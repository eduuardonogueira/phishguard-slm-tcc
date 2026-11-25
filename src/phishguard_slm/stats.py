"""T4: estatistica da comparacao entre modelos (``phishguard exp stats``).

Le as probabilidades por URL gravadas pelo ``exp eval`` (``outputs/runs/<run>/scores``
e ``val_scores.csv``) e produz, por dataset:

1. IC de 95% por bootstrap (percentil) para AP, F1, precisao, recall e FPR no
   limiar da validacao (Efron & Tibshirani, 1993). A reamostragem e por DOMINIO
   registrado (bootstrap de clusters; Field & Welsh, 2007): URLs do mesmo dominio
   nao sao independentes (ex.: dezenas de anuncios de um mesmo CDN) e reamostrar
   URL a URL daria IC estreitos demais.
2. Ponto de operacao: limiar escolhido NA VALIDACAO para precisao >= alvo na
   prevalencia do teste realista (precisao ajustada pela prevalencia), aplicado
   ao teste realista -> recall, precisao e FPR com IC (Axelsson, 2000;
   Whittaker et al., 2010). O teste nunca escolhe limiar (Arp et al., 2022).
3. Comparacoes pareadas no mesmo teste (mesmas URLs):
   - bootstrap pareado da diferenca de AP e de F1 (Koehn, 2004;
     Berg-Kirkpatrick et al., 2012);
   - McNemar sobre os acertos de cada modelo no seu limiar (Dietterich, 1998),
     na versao para dados agrupados por dominio (Durkalski et al., 2003);
   - p-valores corrigidos por Holm dentro de cada dataset e teste (Holm, 1979).

A familia de comparacoes e fixada antes de olhar os resultados: no mesmo modelo,
``todas`` x ``corr`` e ``todas`` x ``url``; no mesmo conjunto de features, cada par de
modelos.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from .config import LABEL_COLUMN, URL_COLUMN

ALPHA = 0.05


# ---------------------------------------------------------------------------
# Metricas vetorizadas (rapidas para o bootstrap)
# ---------------------------------------------------------------------------
def average_precision(y: np.ndarray, p: np.ndarray) -> float:
    """AP igual ao sklearn.average_precision_score (empates no mesmo limiar)."""
    pos = y.sum()
    if pos == 0 or pos == len(y):
        return float("nan")
    order = np.argsort(-p, kind="mergesort")
    ps, ys = p[order], y[order]
    idx = np.r_[np.flatnonzero(np.diff(ps)), len(ps) - 1]
    tps = np.cumsum(ys)[idx]
    fps = idx + 1 - tps
    prec = tps / (tps + fps)
    rec = tps / pos
    return float(np.sum(np.diff(np.r_[0.0, rec]) * prec))


def at_threshold(y: np.ndarray, p: np.ndarray, thr: float) -> dict:
    pred = p >= thr
    tp = int(np.sum(pred & (y == 1)))
    fp = int(np.sum(pred & (y == 0)))
    fn = int(np.sum(~pred & (y == 1)))
    tn = int(np.sum(~pred & (y == 0)))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": prec, "recall": rec, "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
            "fpr": fp / (fp + tn) if fp + tn else 0.0}


def operating_threshold(yv: np.ndarray, pv: np.ndarray, prevalence: float, target: float) -> float | None:
    """Menor limiar (maior recall) cuja precisao, ajustada para ``prevalence``, e >= ``target``.

    precisao(pi) = TPR*pi / (TPR*pi + FPR*(1-pi)): a validacao tem outra proporcao
    de phishing que o cenario realista, entao a precisao e recalculada para ele.
    """
    best = None
    for thr in np.unique(pv)[::-1]:
        pred = pv >= thr
        tpr = np.mean(pred[yv == 1])
        fpr = np.mean(pred[yv == 0])
        den = tpr * prevalence + fpr * (1 - prevalence)
        if den > 0 and tpr * prevalence / den >= target:
            best = float(thr)
    return best


def _ci(samples: np.ndarray) -> tuple[float, float]:
    s = samples[~np.isnan(samples)]
    if not len(s):
        return float("nan"), float("nan")
    return float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))


def _boot_p(delta: np.ndarray) -> float:
    """p bilateral do bootstrap pareado: com que frequencia a diferenca troca de sinal."""
    d = delta[~np.isnan(delta)]
    if not len(d):
        return float("nan")
    # Com B reamostragens, a menor p distinguivel e 1/B (nunca reporta 0).
    return float(min(1.0, max(1.0 / len(d), 2 * min(np.mean(d <= 0), np.mean(d >= 0)))))


def mcnemar(ok_a: np.ndarray, ok_b: np.ndarray, clusters: np.ndarray) -> dict:
    """McNemar para pares agrupados (Durkalski et al., 2003).

    X2 = (soma_k (b_k - c_k))^2 / soma_k (b_k - c_k)^2, com b_k/c_k as discordancias
    no dominio k. Com 1 URL por dominio vira o McNemar classico (b-c)^2/(b+c).
    """
    from scipy.stats import chi2

    disc_ab = ok_a & ~ok_b  # A acerta, B erra
    disc_ba = ~ok_a & ok_b
    b, c = int(disc_ab.sum()), int(disc_ba.sum())
    d = pd.Series(disc_ab.astype(int) - disc_ba.astype(int)).groupby(clusters).sum().to_numpy()
    den = float(np.sum(d ** 2))
    p = 1.0 if den == 0 else float(chi2.sf(float(d.sum()) ** 2 / den, 1))
    return {"a_acerta_b_erra": b, "a_erra_b_acerta": c,
            "dominios_discordantes": int(np.count_nonzero(d)), "p_mcnemar": p}


def cluster_indices(clusters: np.ndarray, n_boot: int, rng: np.random.Generator,
                    subset: np.ndarray | None = None) -> list[np.ndarray]:
    """Indices de cada reamostragem: sorteia DOMINIOS com reposicao e leva todas as URLs deles."""
    pos = np.arange(len(clusters)) if subset is None else np.flatnonzero(subset)
    if not len(pos):
        return []
    codes, uniq = pd.factorize(clusters[pos])
    order = np.argsort(codes, kind="stable")
    starts = np.r_[0, np.cumsum(np.bincount(codes))]
    members = [pos[order[starts[k]:starts[k + 1]]] for k in range(len(uniq))]
    out = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(members), size=len(members))
        out.append(np.concatenate([members[k] for k in pick]))
    return out


def holm(pvals: list[float]) -> list[float]:
    p = np.asarray(pvals, float)
    out = np.full(len(p), np.nan)
    ok = ~np.isnan(p)
    idx = np.flatnonzero(ok)
    order = idx[np.argsort(p[idx])]
    m = len(order)
    running = 0.0
    for k, i in enumerate(order):
        running = max(running, min(1.0, (m - k) * p[i]))
        out[i] = running
    return out.tolist()


# ---------------------------------------------------------------------------
# Leitura dos runs
# ---------------------------------------------------------------------------
class RunScores:
    def __init__(self, run_dir: Path, dataset: str):
        self.name = run_dir.name
        self.man = json.loads((run_dir / "manifest.json").read_text())
        ev = json.loads((run_dir / "evals" / f"{dataset}.json").read_text())
        self.thr = float(ev["limiar_validacao"])
        sc = run_dir / "scores"
        self.test = pd.read_csv(sc / f"{dataset}_teste.csv")
        self.real = pd.read_csv(sc / f"{dataset}_realista.csv")
        vp = run_dir / "val_scores.csv"
        self.val = pd.read_csv(vp) if vp.exists() else None

    @property
    def model(self) -> str:
        return self.man["modelo"]

    @property
    def features(self) -> str:
        return self.man["features"]


def load_runs(runs_dir: Path, dataset: str) -> tuple[list[RunScores], list[str]]:
    ok, missing = [], []
    for rd in sorted(runs_dir.glob("*/manifest.json")):
        man = json.loads(rd.read_text())
        if man.get("dataset") != dataset or man.get("status") != "concluido" or "__smoke" in rd.parent.name:
            continue
        if not (rd.parent / "scores" / f"{dataset}_teste.csv").exists():
            missing.append(rd.parent.name)
            continue
        ok.append(RunScores(rd.parent, dataset))
    return ok, missing


def _aligned(runs: list[RunScores], attr: str) -> tuple[np.ndarray, dict[str, np.ndarray], pd.DataFrame]:
    """Alinha as probabilidades de todos os runs pela URL (mesmo teste, mesma ordem)."""
    base = getattr(runs[0], attr)[[URL_COLUMN, LABEL_COLUMN] + (["conferido"] if "conferido" in
                                                                   getattr(runs[0], attr) else [])]
    probs = {}
    for r in runs:
        df = getattr(r, attr)
        if len(df) != len(base) or set(df[URL_COLUMN]) != set(base[URL_COLUMN]):
            raise RuntimeError(f"{r.name}: o teste nao tem as mesmas URLs dos outros runs; reavalie")
        probs[r.name] = df.set_index(URL_COLUMN)["prob"].reindex(base[URL_COLUMN]).to_numpy()
    return base[LABEL_COLUMN].to_numpy().astype(int), probs, base


# ---------------------------------------------------------------------------
# Analise
# ---------------------------------------------------------------------------
def default_pairs(runs: list[RunScores]) -> list[tuple[str, str]]:
    by = {(r.model, r.features): r.name for r in runs}
    models = sorted({r.model for r in runs}, key=lambda m: ["qwen05b", "gemma1b", "xgb"].index(m)
                    if m in ("qwen05b", "gemma1b", "xgb") else 9)
    pairs = []
    for m in models:  # mesmo modelo: o que as features acrescentam
        for other in ("corr", "url"):
            if (m, "todas") in by and (m, other) in by:
                pairs.append((by[(m, "todas")], by[(m, other)]))
    for fs in ("todas", "corr", "url"):  # mesmas features: qual modelo
        for a, b in combinations(models, 2):
            if (a, fs) in by and (b, fs) in by:
                pairs.append((by[(a, fs)], by[(b, fs)]))
    return pairs


def analyze(runs_dir: Path, dataset: str, n_boot: int = 2000, target_precision: float = 0.9,
            seed: int = 42, pairs: list[tuple[str, str]] | None = None,
            groups: dict[str, str] | None = None) -> dict:
    """``groups``: URL -> dominio registrado (o mesmo da particao). Sem ele, cada URL e um grupo."""
    runs, missing = load_runs(runs_dir, dataset)
    if not runs:
        return {"dataset": dataset, "runs": pd.DataFrame(), "pares": pd.DataFrame(), "faltando": missing}
    rng = np.random.default_rng(seed)
    y, probs, base = _aligned(runs, "test")
    yr, probs_r, base_r = _aligned(runs, "real")
    prevalence = float(yr.mean())
    gold = (base["conferido"].to_numpy() == 1) if "conferido" in base else np.zeros(len(y), bool)
    groups = groups or {}
    cl = base[URL_COLUMN].map(groups).fillna(base[URL_COLUMN]).to_numpy()
    cl_r = base_r[URL_COLUMN].map(groups).fillna(base_r[URL_COLUMN]).to_numpy()
    idx = cluster_indices(cl, n_boot, rng)
    idx_r = cluster_indices(cl_r, n_boot, rng)
    idx_g = cluster_indices(cl, n_boot, rng, subset=gold) or None

    rows = []
    for r in runs:
        p, pr = probs[r.name], probs_r[r.name]
        row = {"run": r.name, "modelo": r.model, "features": r.features, "limiar_val": r.thr}
        point = {"ap": average_precision(y, p), **at_threshold(y, p, r.thr)}
        boot = {k: np.empty(n_boot) for k in point}
        for b in range(n_boot):
            ii = idx[b]
            boot["ap"][b] = average_precision(y[ii], p[ii])
            for k, v in at_threshold(y[ii], p[ii], r.thr).items():
                boot[k][b] = v
        for k, v in point.items():
            lo, hi = _ci(boot[k])
            row[k], row[f"{k}_ic_inf"], row[f"{k}_ic_sup"] = v, lo, hi
        # Concentracao dos falsos positivos: poucos dominios respondem pela maioria?
        fp_dom = pd.Series(cl[(p >= r.thr) & (y == 0)]).value_counts()
        row["fp_n"], row["fp_dominios"] = int(fp_dom.sum()), int(len(fp_dom))
        row["fp_top2_dominios"] = ", ".join(f"{d} ({n})" for d, n in fp_dom.head(2).items())
        row["fp_pct_top2"] = float(fp_dom.head(2).sum() / fp_dom.sum()) if len(fp_dom) else 0.0

        if idx_g is not None:  # subconjunto conferido manualmente
            gp = at_threshold(y[gold], p[gold], r.thr)
            gb = np.array([at_threshold(y[ii], p[ii], r.thr)["f1"] for ii in idx_g])
            row["f1_conferido"], (row["f1_conferido_ic_inf"], row["f1_conferido_ic_sup"]) = gp["f1"], _ci(gb)
            row["fpr_conferido"] = gp["fpr"]
            row["n_conferido"] = int(gold.sum())

        # Ponto de operacao: limiar da VALIDACAO para precisao >= alvo na prevalencia realista.
        thr_op = None
        if r.val is not None:
            thr_op = operating_threshold(r.val[LABEL_COLUMN].to_numpy().astype(int), r.val["prob"].to_numpy(),
                                         prevalence, target_precision)
        row["limiar_operacao"] = thr_op
        if thr_op is not None:
            op = at_threshold(yr, pr, thr_op)
            ob = {k: np.empty(n_boot) for k in ("recall", "precision", "fpr")}
            for b in range(n_boot):
                m = at_threshold(yr[idx_r[b]], pr[idx_r[b]], thr_op)
                for k in ob:
                    ob[k][b] = m[k]
            for k in ob:
                lo, hi = _ci(ob[k])
                row[f"op_{k}"], row[f"op_{k}_ic_inf"], row[f"op_{k}_ic_sup"] = op[k], lo, hi
        rows.append(row)
    runs_df = pd.DataFrame(rows).sort_values("ap", ascending=False).reset_index(drop=True)

    by = {r.name: r for r in runs}
    pairs = [(a, b) for a, b in (pairs or default_pairs(runs)) if a in by and b in by]
    prow = []
    for a, b in pairs:
        pa, pb = probs[a], probs[b]
        ta, tb = by[a].thr, by[b].thr
        d_ap, d_f1 = np.empty(n_boot), np.empty(n_boot)
        for k in range(n_boot):
            ii = idx[k]
            d_ap[k] = average_precision(y[ii], pa[ii]) - average_precision(y[ii], pb[ii])
            d_f1[k] = at_threshold(y[ii], pa[ii], ta)["f1"] - at_threshold(y[ii], pb[ii], tb)["f1"]
        ok_a, ok_b = (pa >= ta) == (y == 1), (pb >= tb) == (y == 1)
        prow.append({
            "a": a, "b": b,
            "delta_ap": average_precision(y, pa) - average_precision(y, pb),
            "delta_ap_ic_inf": _ci(d_ap)[0], "delta_ap_ic_sup": _ci(d_ap)[1], "p_ap": _boot_p(d_ap),
            "delta_f1": at_threshold(y, pa, ta)["f1"] - at_threshold(y, pb, tb)["f1"],
            "delta_f1_ic_inf": _ci(d_f1)[0], "delta_f1_ic_sup": _ci(d_f1)[1], "p_f1": _boot_p(d_f1),
            **mcnemar(ok_a, ok_b, cl),
        })
    pares = pd.DataFrame(prow)
    if len(pares):
        for col in ("p_ap", "p_f1", "p_mcnemar"):
            pares[f"{col}_holm"] = holm(pares[col].tolist())
        pares["diferenca_ap"] = np.where(pares["p_ap_holm"] < ALPHA, "significativa", "empate")
        pares["diferenca_erros"] = np.where(pares["p_mcnemar_holm"] < ALPHA, "significativa", "empate")
    return {"dataset": dataset, "runs": runs_df, "pares": pares, "faltando": missing,
            "prevalencia_realista": prevalence, "n_teste": len(y), "n_realista": len(yr),
            "n_dominios": int(pd.Series(cl).nunique()),
            "n_boot": n_boot, "precisao_alvo": target_precision, "seed": seed}


# ---------------------------------------------------------------------------
# Relatorio
# ---------------------------------------------------------------------------
def _f(v, nd=3) -> str:
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{nd}f}"


def _ic(row, k, nd=3) -> str:
    if k not in row or pd.isna(row.get(k)):
        return ""
    return f"{_f(row[k], nd)} [{_f(row[f'{k}_ic_inf'], nd)}, {_f(row[f'{k}_ic_sup'], nd)}]"


def _p(v) -> str:
    return "" if v is None or pd.isna(v) else ("<0.001" if v < 0.001 else f"{v:.3f}")


METHOD_MD = """\
## Metodo

- **IC de 95%**: bootstrap percentil com {n_boot} reamostragens (Efron & Tibshirani, 1993), sorteando
  **dominios** e nao URLs (bootstrap de clusters; Field & Welsh, 2007): URLs do mesmo dominio nao sao
  independentes, e a particao tambem e por dominio.
- **Limiar**: o de melhor F1 na validacao; o teste nunca escolhe limiar (Arp et al., 2022).
- **Ponto de operacao**: limiar escolhido na validacao para precisao >= {alvo:.0%} na prevalencia
  do teste realista ({prev:.1%} de phishing), aplicado ao teste realista (Axelsson, 2000;
  Whittaker et al., 2010). Sem limiar = a validacao nao atinge essa precisao.
- **Comparacoes** (mesmas URLs): bootstrap pareado (por dominio) da diferenca de AP e de F1 (Koehn, 2004;
  Berg-Kirkpatrick et al., 2012) e McNemar sobre os acertos (Dietterich, 1998) na versao para dados
  agrupados (Durkalski et al., 2003), com correcao
  de Holm (1979) dentro do dataset. Familia fixada antes dos resultados: mesmo modelo
  (todas x corr, todas x url) e mesmas features (cada par de modelos).
- **Leitura**: "empate" = nao ha evidencia de diferenca com alfa = 0,05 apos Holm. Com {n_boot}
  reamostragens, o menor p do bootstrap e 1/{n_boot} antes da correcao.
"""


def to_markdown(res: dict) -> str:
    d = res["dataset"]
    out = [f"# Estatistica - teste {d}", ""]
    if res["runs"].empty:
        return "\n".join(out + ["Sem runs com probabilidades salvas."])
    out.append(f"Teste: {res['n_teste']} URLs de {res['n_dominios']} dominios; realista: {res['n_realista']} "
               f"({res['prevalencia_realista']:.1%} phishing).\n")
    out.append(METHOD_MD.format(n_boot=res["n_boot"], alvo=res["precisao_alvo"], prev=res["prevalencia_realista"]))
    gold = "f1_conferido" in res["runs"]
    out += ["## Por run (IC 95%)", "",
            "| run | AP | F1 | FPR | recall | " + ("F1 conferidas | " if gold else "")
            + f"realista no limiar p/ P>={res['precisao_alvo']:.0%} (val): recall | precisao | FPR |",
            "|---|---|---|---|---|" + ("---|" if gold else "") + "---|---|---|"]
    for _, r in res["runs"].iterrows():
        out.append(f"| {r['run']} | {_ic(r, 'ap')} | {_ic(r, 'f1')} | {_ic(r, 'fpr')} | {_ic(r, 'recall')} | "
                   + (f"{_ic(r, 'f1_conferido')} | " if gold else "")
                   + (f"{_ic(r, 'op_recall')} | {_ic(r, 'op_precision')} | {_ic(r, 'op_fpr')} |"
                      if pd.notna(r.get("limiar_operacao")) else "sem limiar | | |"))
    out += ["", "## Concentracao dos falsos positivos (teste, limiar da validacao)", "",
            "| run | FP | dominios com FP | % dos FP nos 2 maiores | 2 maiores |", "|---|---|---|---|---|"]
    for _, r in res["runs"].iterrows():
        out.append(f"| {r['run']} | {r['fp_n']} | {r['fp_dominios']} | {r['fp_pct_top2']:.0%} | {r['fp_top2_dominios']} |")
    if len(res["pares"]):
        out += ["", "## Comparacoes pareadas (A - B; p corrigido por Holm)", "",
                "| A | B | dAP [IC] | p AP | dF1 [IC] | p F1 | A ok/B erra : A erra/B ok (dominios) | p McNemar | AP | erros |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in res["pares"].iterrows():
            out.append(
                f"| {r['a']} | {r['b']} | {_f(r['delta_ap'], 4)} [{_f(r['delta_ap_ic_inf'], 4)}, "
                f"{_f(r['delta_ap_ic_sup'], 4)}] | {_p(r['p_ap_holm'])} | {_f(r['delta_f1'], 4)} "
                f"[{_f(r['delta_f1_ic_inf'], 4)}, {_f(r['delta_f1_ic_sup'], 4)}] | {_p(r['p_f1_holm'])} | "
                f"{r['a_acerta_b_erra']} : {r['a_erra_b_acerta']} ({r['dominios_discordantes']}) | {_p(r['p_mcnemar_holm'])} | "
                f"{r['diferenca_ap']} | {r['diferenca_erros']} |")
    out += ["", "## Referencias", "",
            "- Arp, D. et al. Dos and Don'ts of Machine Learning in Computer Security. USENIX Security, 2022.",
            "- Axelsson, S. The base-rate fallacy and the difficulty of intrusion detection. ACM TISSEC, 2000.",
            "- Berg-Kirkpatrick, T. et al. An Empirical Investigation of Statistical Significance in NLP. EMNLP-CoNLL, 2012.",
            "- Dietterich, T. Approximate Statistical Tests for Comparing Supervised Classification Learning "
            "Algorithms. Neural Computation, 1998.",
            "- Durkalski, V. L. et al. Analysis of clustered matched-pair data. Statistics in Medicine, 2003.",
            "- Efron, B.; Tibshirani, R. An Introduction to the Bootstrap. Chapman & Hall, 1993.",
            "- Field, C. A.; Welsh, A. H. Bootstrapping clustered data. J. R. Statist. Soc. B, 2007.",
            "- Holm, S. A simple sequentially rejective multiple test procedure. Scand. J. Statistics, 1979.",
            "- Koehn, P. Statistical Significance Tests for Machine Translation Evaluation. EMNLP, 2004.",
            "- Whittaker, C.; Ryner, B.; Nazif, M. Large-Scale Automatic Classification of Phishing Pages. NDSS, 2010.",
            ""]
    return "\n".join(out)


def write(res: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    d = res["dataset"]
    paths = [out_dir / f"{d}_runs.csv", out_dir / f"{d}_pares.csv", out_dir / f"{d}.md"]
    res["runs"].round(4).to_csv(paths[0], index=False)
    res["pares"].round(5).to_csv(paths[1], index=False)
    paths[2].write_text(to_markdown(res))
    return paths
