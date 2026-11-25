"""Matriz de experimentos: treina cada combinacao uma vez e avalia em todos os testes.

Eixos:
  modelo    qwen05b (Qwen2.5-0.5B-Instruct + LoRA), gemma1b (Gemma 3 1B + LoRA),
            xgb (XGBoost, baseline do paper reproduzido nas mesmas particoes)
  dataset   paper (Phishing Guardian) | br (auditoria BR com features calculadas)
  features  todas (13) | corr (selecionadas pela correlacao) | url (so a URL)

Para o XGBoost, "url" sao as 8 features lexicas: ele nao le texto, entao usa o
que sai so da string da URL. O SLM le a URL crua.

Cada run fica em ``outputs/runs/<modelo>__<dataset>__<features>/``:
  manifest.json      o que foi treinado: hashes do dataset e da particao, features,
                     hiperparametros, commit do git, tempo de treino
  adapter/ | model.json   pesos (fora do git)
  val_scores.csv     probabilidades na validacao do proprio dataset (fora do git)
  evals/<teste>.json metricas em cada conjunto de teste (paper, br)
  operational.json   latencia em CPU e tamanho
  errors/<teste>.csv falsos positivos/negativos (fora do git: contem URLs)

Particoes: ``datasets/splits/<dataset>.csv`` (url -> train/val/test), por dominio
registrado (nenhum dominio em dois splits) e estratificadas pelo rotulo. Neste
repositorio as duas sao as do TCC, congeladas: a do paper vem versionada e a do BR
vem da coluna ``split`` do PhishBR-URL (ver dados.py). Se o dataset mudar, o hash
nao bate e o run recusa.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import FEATURE_COLUMNS, LABEL_COLUMN, OUTPUTS, ROOT, URL_COLUMN, Config
from .featurize import LEXICAL, from_paper_scale, lexical_agreement, to_paper_scale

# Cada dataset tem duas versoes com as MESMAS linhas:
#   bruto        unidades originais (caracteres, dias, PageRank 0-10) -> SLMs
#   normalizado  escala do paper (divisores fixos, ver featurize.py)  -> ML (XGBoost)
# Nomes iguais nos dois: dataset.csv (bruto) e dataset_normalizado.csv.
# paper: o original e o normalizado; o bruto e derivado.
# br:    o original e o bruto; o normalizado e derivado.
DATASETS = {
    "paper": {
        "bruto": ROOT / "datasets" / "paper" / "dataset.csv",
        "normalizado": ROOT / "datasets" / "paper" / "dataset_normalizado.csv",
    },
    "br": {
        "bruto": ROOT / "datasets" / "br" / "dataset.csv",
        "normalizado": ROOT / "datasets" / "br" / "dataset_normalizado.csv",
    },
}
ORIGINAL = {"paper": "normalizado", "br": "bruto"}
_GEN_CMD = {"paper": "phishguard dados", "br": "phishguard dados"}
PAPER_RAW = DATASETS["paper"]["normalizado"]
PAPER_REF_DATE = "2024-04-30"  # inferida de activate_days (ver featurize.py)
SPLITS_DIR = ROOT / "datasets" / "splits"
FEATURE_SETS_JSON = SPLITS_DIR / "feature_sets.json"
RUNS_DIR = OUTPUTS / "runs"
LEADERBOARD_CSV = OUTPUTS / "leaderboard.csv"
LEADERBOARD_MD = OUTPUTS / "leaderboard.md"

MODELS = {
    "qwen05b": "Qwen/Qwen2.5-0.5B-Instruct",
    "gemma1b": "google/gemma-3-1b-it",
    "xgb": "xgboost",
}
FEATURE_SET_NAMES = ("todas", "corr", "url")

# Resultado publicado (Guarizi et al., SBSeg 2025): XGBoost, 13 atributos,
# particao aleatoria 85/15. Referencia historica, nao comparavel diretamente.
PAPER_PUBLISHED = {
    "run": "publicado (artigo)", "modelo": "xgb", "treino": "paper", "features": "todas",
    "teste": "paper (aleatoria 85/15)", "accuracy": 0.9951, "precision": 0.9958,
    "recall": 0.9931, "f1": 0.9945,
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    return {"commit": run("rev-parse", "HEAD"), "sujo": bool(run("status", "--porcelain", "src"))}


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------
def model_version(model: str) -> str:
    """Versao do dataset que cada modelo le: ML normalizado, SLM bruto."""
    return "normalizado" if model == "xgb" else "bruto"


def available() -> list[str]:
    return [n for n, v in DATASETS.items() if v["bruto"].exists()]


def _write_derived(df: pd.DataFrame, name: str) -> Path:
    """Grava a versao derivada + sidecar com o hash do original de onde saiu."""
    orig_v = ORIGINAL[name]
    der_v = "bruto" if orig_v == "normalizado" else "normalizado"
    path = DATASETS[name][der_v]
    df.to_csv(path, index=False)
    path.with_suffix(".json").write_text(json.dumps({
        "derivado_de": str(DATASETS[name][orig_v].relative_to(ROOT)),
        "origem_sha256": _sha256(DATASETS[name][orig_v]),
        "versao": der_v,
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }, indent=1))
    return path


def _check_derived(name: str) -> None:
    orig_v = ORIGINAL[name]
    der = DATASETS[name]["bruto" if orig_v == "normalizado" else "normalizado"]
    side = der.with_suffix(".json")
    if not side.exists() or json.loads(side.read_text())["origem_sha256"] != _sha256(DATASETS[name][orig_v]):
        cmd = "phishguard dados"
        raise RuntimeError(f"{der.name} esta desatualizado em relacao a {DATASETS[name][orig_v].name}; rode `{cmd}`")


def normalize_br() -> Path:
    """br/dataset_normalizado.csv: br/dataset.csv na escala do paper, para os modelos de ML."""
    df = pd.read_csv(DATASETS["br"]["bruto"], low_memory=False)
    return _write_derived(to_paper_scale(df), "br")


def build_paper_dataset() -> dict:
    """paper/dataset.csv: o original do paper (dataset_normalizado.csv) em unidades brutas,
    para os SLMs, + dominio para a particao."""
    from .dominios import domain_info
    from .data import load_dataset

    raw = load_dataset(PAPER_RAW)
    df = from_paper_scale(raw)
    df["dominio"] = df[URL_COLUMN].map(lambda u: domain_info(u)["reg_domain_private"])
    df["data_ref"] = PAPER_REF_DATE
    cols = [URL_COLUMN, LABEL_COLUMN, "dominio", "data_ref", *FEATURE_COLUMNS]
    _write_derived(df[cols], "paper")
    agree = lexical_agreement(df)
    report = {
        "origem": str(PAPER_RAW.relative_to(ROOT)),
        "origem_sha256": _sha256(PAPER_RAW),
        "linhas": len(df),
        "phishing": int(df[LABEL_COLUMN].sum()),
        "dominios": int(df["dominio"].nunique()),
        "concordancia_lexica": agree,
    }
    out = PAPER_RAW.with_name("validacao_features.json")
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return report


def load(name: str, version: str = "bruto") -> pd.DataFrame:
    path = DATASETS[name][version]
    if not path.exists():
        hint = _GEN_CMD.get(name, "phishguard dados")
        raise FileNotFoundError(f"{path} nao existe; gere com `{hint}`")
    _check_derived(name)
    if name == "paper" and version == "normalizado":
        from .data import load_dataset

        return load_dataset(path)  # mesma limpeza usada para gerar o bruto
    return pd.read_csv(path, low_memory=False)


# ---------------------------------------------------------------------------
# Particoes congeladas
# ---------------------------------------------------------------------------
def make_splits(name: str, seed: int = 42, force: bool = False) -> dict:
    """70/15/15 por dominio, estratificado (StratifiedGroupKFold com 20 dobras)."""
    from sklearn.model_selection import StratifiedGroupKFold

    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    out = SPLITS_DIR / f"{name}.csv"
    meta_path = SPLITS_DIR / f"{name}.json"
    if out.exists() and not force:
        raise FileExistsError(f"{out} ja existe (congelada). Use --force so se quiser invalidar os runs.")
    df = load(name)
    groups = df["dominio"].fillna(df[URL_COLUMN])
    # Linhas com rotulo conferido manualmente (BR) vao para o teste, junto com
    # todo o dominio delas: o teste ganha um subconjunto "ouro" sem vazamento.
    gold = df["conferido"].fillna(0).astype(int) == 1 if "conferido" in df else pd.Series(False, index=df.index)
    forced = groups.isin(set(groups[gold]))
    split = np.full(len(df), "train", dtype=object)
    split[forced.to_numpy()] = "test"
    rest = df.index[~forced]
    n_folds = 20
    folds = np.empty(len(rest), dtype=int)
    sgkf = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    for k, (_, idx) in enumerate(sgkf.split(rest, df.loc[rest, LABEL_COLUMN], groups[rest])):
        folds[idx] = k
    # completa o teste ate ~15% do total e reserva ~15% para a validacao
    fold_size = max(1, len(rest) / n_folds)
    n_test = max(0, round((0.15 * len(df) - forced.sum()) / fold_size))
    split[rest[folds < n_test]] = "test"
    split[rest[(folds >= n_test) & (folds < n_test + 3)]] = "val"
    pd.DataFrame({URL_COLUMN: df[URL_COLUMN], "split": split}).to_csv(out, index=False)
    df = df.assign(split=split, grupo=groups)
    meta = {
        "dataset": name,
        "dataset_sha256": _sha256(DATASETS[name]["bruto"]),
        "splits_sha256": _sha256(out),
        "seed": seed,
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "contagem": {
            s: {"total": int((df.split == s).sum()), "phishing": int(df[df.split == s][LABEL_COLUMN].sum()),
                "dominios": int(df[df.split == s].grupo.nunique())}
            for s in ("train", "val", "test")
        },
        "dominios_em_mais_de_um_split": int((df.groupby("grupo").split.nunique() > 1).sum()),
        "conferidas_no_teste": int(gold.sum()),
        "linhas_forcadas_no_teste": int(forced.sum()),
    }
    meta_path.write_text(json.dumps(meta, indent=1))
    return meta


def load_splits(name: str, cfg: Config | None = None, version: str = "bruto") -> dict[str, pd.DataFrame]:
    from .data import make_realistic_test

    cfg = cfg or Config()
    path, meta_path = SPLITS_DIR / f"{name}.csv", SPLITS_DIR / f"{name}.json"
    if not path.exists():
        print(f"[exp] particao de '{name}' ainda nao existe: criando e congelando")
        make_splits(name, seed=cfg.seed)
    meta = json.loads(meta_path.read_text())
    if meta["dataset_sha256"] != _sha256(DATASETS[name]["bruto"]):
        raise RuntimeError(
            f"{DATASETS[name]['bruto'].name} mudou depois que a particao foi congelada. Os runs antigos "
            f"nao sao comparaveis com o novo dado: rode `phishguard exp splits {name} --force` "
            "e treine de novo."
        )
    sp = pd.read_csv(path)
    df = load(name, version).merge(sp, on=URL_COLUMN, how="inner")
    if len(df) != len(sp):
        raise RuntimeError(f"{DATASETS[name][version].name}: {len(df)} linhas casam com a particao de {len(sp)}")
    out = {s: df[df.split == s].drop(columns="split").reset_index(drop=True) for s in ("train", "val", "test")}
    out["test_realistic"] = make_realistic_test(out["test"], cfg.realistic_phishing_rate, cfg.seed)
    return out


# ---------------------------------------------------------------------------
# Conjuntos de features
# ---------------------------------------------------------------------------
def feature_sets_path(dataset: str) -> Path:
    return FEATURE_SETS_JSON if dataset == "paper" else SPLITS_DIR / f"feature_sets_{dataset}.json"


def select_corr(dataset: str = "paper", min_label: float = 0.2, max_pair: float = 0.6,
                force: bool = False) -> dict:
    """Seleciona features pela correlacao de Spearman, no TREINO do proprio dataset.

    1. descarta as fracas: |rho com o rotulo| < ``min_label``;
    2. das restantes (da mais forte para a mais fraca), descarta a redundante:
       |rho com uma ja escolhida| >= ``max_pair``.
    Cada dataset tem o seu conjunto: nada do paper entra na escolha do BR.
    Vazios (NaN) ficam fora do calculo de cada par.
    """
    path = feature_sets_path(dataset)
    if path.exists() and not force:
        return json.loads(path.read_text())
    train = load_splits(dataset)["train"]
    corr = train[[*FEATURE_COLUMNS, LABEL_COLUMN]].astype(float).corr("spearman")
    with_label = corr[LABEL_COLUMN].drop(LABEL_COLUMN)
    ranked = with_label.abs().sort_values(ascending=False)
    chosen, dropped = [], {}
    for feat, r in ranked.items():
        if r < min_label:
            dropped[feat] = f"fraca: |rho|={r:.3f} < {min_label}"
            continue
        clash = [c for c in chosen if abs(corr.loc[feat, c]) >= max_pair]
        if clash:
            dropped[feat] = f"redundante com {clash[0]}: |rho|={abs(corr.loc[feat, clash[0]]):.3f}"
            continue
        chosen.append(feat)
    res = {
        "criterio": {"metodo": "spearman", "base": f"{dataset}/train", "min_com_rotulo": min_label,
                     "max_entre_features": max_pair},
        "rho_com_rotulo": {k: round(float(v), 4) for k, v in with_label.items()},
        "sets": {"todas": list(FEATURE_COLUMNS), "corr": chosen, "url": []},
        "descartadas_corr": dropped,
    }
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    return res


def feature_columns(fs: str, model: str, dataset: str) -> list[str]:
    cols = select_corr(dataset)["sets"][fs]
    if model == "xgb" and fs == "url":
        return list(LEXICAL)
    return cols


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------
def data_fingerprint(dataset: str, version: str) -> dict:
    """Hashes que identificam o dado de um dataset: arquivo da versao + particao."""
    split = SPLITS_DIR / f"{dataset}.csv"
    path = DATASETS[dataset][version]
    return {"dataset_sha256": _sha256(path) if path.exists() else None,
            "splits_sha256": _sha256(split) if split.exists() else None}


def train_stale(man: dict) -> str | None:
    """Motivo pelo qual um run concluido ficou velho (dado ou particao mudaram)."""
    now = data_fingerprint(man["dataset"], man.get("versao_dataset", model_version(man["modelo"])))
    if man.get("dataset_sha256") != now["dataset_sha256"]:
        return f"{man['dataset']} mudou desde o treino"
    if man.get("splits_sha256") != now["splits_sha256"]:
        return f"a particao de {man['dataset']} mudou desde o treino"
    if man.get("feature_columns") != feature_columns(man["features"], man["modelo"], man["dataset"]):
        return f"o conjunto '{man['features']}' de {man['dataset']} mudou desde o treino"
    return None


def eval_stale(res: dict, version: str) -> bool:
    """Avaliacao feita sobre um teste que mudou depois (ou antes do registro dos hashes)."""
    return res.get("teste_hashes") != data_fingerprint(res["teste"], version)


def run_name(model: str, dataset: str, fs: str) -> str:
    return f"{model}__{dataset}__{fs}"


def _manifest(run_dir: Path) -> dict | None:
    p = run_dir / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else None


def train_run(model: str, dataset: str, fs: str, cfg: Config, force: bool = False) -> Path:
    # Treino com amostra limitada vira outro run (sufixo __smoke): nunca e
    # confundido com o treino completo nem o sobrescreve.
    suffix = "__smoke" if cfg.max_train_samples else ""
    run_dir = RUNS_DIR / (run_name(model, dataset, fs) + suffix)
    man = _manifest(run_dir)
    if man and man.get("status") == "concluido" and not force:
        why = train_stale(man)
        if not why:
            print(f"[exp] {run_dir.name} ja treinado ({man['fim']}); pulando (use --force para refazer)")
            return run_dir
        print(f"[exp] {run_dir.name}: {why}; retreinando")
    version = model_version(model)
    splits = load_splits(dataset, cfg, version)
    cols = feature_columns(fs, model, dataset)
    run_dir.mkdir(parents=True, exist_ok=True)
    man = {
        "run": run_dir.name, "modelo": model, "model_id": MODELS[model], "dataset": dataset,
        "features": fs, "feature_columns": cols,
        "versao_dataset": version,
        "arquivo_dataset": str(DATASETS[dataset][version].relative_to(ROOT)),
        "dataset_sha256": _sha256(DATASETS[dataset][version]),
        "splits_sha256": _sha256(SPLITS_DIR / f"{dataset}.csv"),
        "git": _git(), "inicio": datetime.now().isoformat(timespec="seconds"), "status": "treinando",
    }
    (run_dir / "manifest.json").write_text(json.dumps(man, indent=1))
    train_df = splits["train"]
    if model == "xgb":
        summary = _train_xgb(train_df, cols, cfg, run_dir)
        man["config"] = {"seed": cfg.seed}
    else:
        from .train import train_lora

        cfg.model_id = MODELS[model]
        summary = train_lora(cfg, train_df=train_df, feature_columns=cols, out_dir=run_dir / "adapter")
        man["config"] = {k: v for k, v in asdict(cfg).items() if not isinstance(v, Path)}
    man.update(treino=summary, status="concluido", fim=datetime.now().isoformat(timespec="seconds"))
    (run_dir / "manifest.json").write_text(json.dumps(man, indent=1, default=str))
    # Avaliacoes antigas deste run deixam de valer.
    for old in (run_dir / "evals").glob("*.json") if (run_dir / "evals").exists() else []:
        old.unlink()
    (run_dir / "val_scores.csv").unlink(missing_ok=True)
    (run_dir / "operational.json").unlink(missing_ok=True)
    return run_dir


XGB_PARAMS = dict(n_estimators=300, max_depth=6, learning_rate=0.1, subsample=1.0,
                  eval_metric="logloss", n_jobs=-1)


def _train_xgb(train_df: pd.DataFrame, cols: list[str], cfg: Config, run_dir: Path) -> dict:
    from xgboost import XGBClassifier

    t0 = time.time()
    clf = XGBClassifier(**XGB_PARAMS, random_state=cfg.seed)
    clf.fit(train_df[cols].astype(float), train_df[LABEL_COLUMN])
    clf.save_model(run_dir / "model.json")
    return {"n_train": len(train_df), "train_seconds": round(time.time() - t0, 1), "params": XGB_PARAMS}


class _Scorer:
    """Interface comum: probabilidade de phishing por linha + latencia por linha."""

    def __init__(self, man: dict, run_dir: Path, cfg: Config, prefer_cpu: bool = False):
        self.cols = man["feature_columns"]
        self.kind = man["modelo"]
        if self.kind == "xgb":
            from xgboost import XGBClassifier

            self.clf = XGBClassifier()
            self.clf.load_model(run_dir / "model.json")
            self.device = "cpu"
        else:
            from .scoring import PhishClassifier

            cfg.model_id = man["model_id"]
            self.clf = PhishClassifier(cfg, adapter_dir=run_dir / "adapter", prefer_cpu=prefer_cpu,
                                       feature_columns=self.cols)
            self.device = self.clf.device

    def score(self, df: pd.DataFrame, desc: str) -> np.ndarray:
        if self.kind == "xgb":
            return self.clf.predict_proba(df[self.cols].astype(float))[:, 1]
        from .evaluate import _predict_frame

        return _predict_frame(self.clf, df, desc=desc)["prob_phishing"].to_numpy()

    def latency(self, df: pd.DataFrame, n: int = 200) -> dict:
        import os

        from rich.progress import track

        rows = df.head(n)
        threads = None
        if self.kind != "xgb":
            # Num servidor com dezenas de nucleos o torch usa todos e as threads
            # disputam entre si (>10 s/URL). Fixa um numero tipico de notebook.
            import torch

            old_threads = torch.get_num_threads()
            threads = int(os.environ.get("PHISHGUARD_LAT_THREADS", "4"))
            torch.set_num_threads(threads)
        try:
            samples = self._latency_samples(rows, track)
        finally:
            if threads is not None:
                torch.set_num_threads(old_threads)
        arr = np.array(samples[3:] or samples)
        return {"device": self.device, "threads": threads, "n": len(arr),
                "p50_ms": round(float(np.percentile(arr, 50)), 2),
                "p95_ms": round(float(np.percentile(arr, 95)), 2)}

    def _latency_samples(self, rows: pd.DataFrame, track) -> list[float]:
        samples = []
        for i in track(range(len(rows)), description=f" latencia {self.device} ({len(rows)} URLs, 1 por vez)"):
            one = rows.iloc[[i]]
            t0 = time.perf_counter()
            if self.kind == "xgb":
                self.clf.predict_proba(one[self.cols].astype(float))
            else:
                self.clf.predict_row(one.iloc[0].to_dict())
            samples.append((time.perf_counter() - t0) * 1000)
        return samples


def _metrics(y: np.ndarray, p: np.ndarray, thr: float) -> dict:
    from sklearn.metrics import average_precision_score

    from .evaluate import _metrics_at

    m = _metrics_at(y, p, thr)
    cm = m["confusion_matrix"]
    m["fpr"] = round(cm["fp"] / max(1, cm["fp"] + cm["tn"]), 4)
    if len(np.unique(y)) > 1:
        m["average_precision"] = round(float(average_precision_score(y, p)), 4)
    return m


def _save_scores(path: Path, df: pd.DataFrame, prob: np.ndarray) -> None:
    path.parent.mkdir(exist_ok=True)
    out = pd.DataFrame({URL_COLUMN: df[URL_COLUMN].to_numpy(), LABEL_COLUMN: df[LABEL_COLUMN].to_numpy(),
                        "prob": np.round(prob, 6)})
    if "conferido" in df:
        out["conferido"] = df["conferido"].fillna(0).astype(int).to_numpy()
    out.to_csv(path, index=False)


def _sample(df: pd.DataFrame, n: int | None, seed: int) -> pd.DataFrame:
    if not n or len(df) <= n:
        return df
    return df.sample(n=n, random_state=seed).reset_index(drop=True)


def eval_run(run: str, tests: list[str], cfg: Config, max_samples: int | None = None,
             force: bool = False) -> list[dict]:
    from .evaluate import _best_f1_threshold

    run_dir = RUNS_DIR / run
    man = _manifest(run_dir)
    if not man or man.get("status") != "concluido":
        raise RuntimeError(f"{run} nao foi treinado (sem manifest concluido)")
    evals = run_dir / "evals"
    evals.mkdir(exist_ok=True)
    version = model_version(man["modelo"])

    def _pending(t: str) -> bool:
        path = evals / f"{t}.json"
        if force or not path.exists():
            return True
        if not (run_dir / "scores" / f"{t}_teste.csv").exists():
            print(f"[exp] {run} -> {t}: faltam as probabilidades por URL (exp stats); reavaliando")
            return True
        if eval_stale(json.loads(path.read_text()), version):
            print(f"[exp] {run} -> {t}: o teste mudou desde a avaliacao; reavaliando")
            return True
        return False

    pending = [t for t in tests if _pending(t)]
    need_op = force or not (run_dir / "operational.json").exists()
    if not pending and not need_op:
        print(f"[exp] {run}: avaliacoes ja existem; pulando")
        return []
    if max_samples:
        print(f"[exp] AVISO: --max-samples {max_samples} (resultado parcial, so para teste rapido)")
    own = load_splits(man["dataset"], cfg, version)
    if man["splits_sha256"] != _sha256(SPLITS_DIR / f"{man['dataset']}.csv"):
        raise RuntimeError(f"a particao de {man['dataset']} mudou depois do treino de {run}; retreine")
    _gpu: list = []

    def scorer() -> _Scorer:  # carrega so se for preciso pontuar algo
        if not _gpu:
            _gpu.append(_Scorer(man, run_dir, cfg))
        return _gpu[0]

    # Limiar: melhor F1 na validacao do dataset de treino (nunca no teste).
    val_path = run_dir / "val_scores.csv"
    val = _sample(own["val"], max_samples, cfg.seed)
    if val_path.exists() and not force and not max_samples:
        vs = pd.read_csv(val_path)
    else:
        vs = pd.DataFrame({URL_COLUMN: val[URL_COLUMN], LABEL_COLUMN: val[LABEL_COLUMN],
                           "prob": scorer().score(val, "validacao")})
        if not max_samples:
            vs.to_csv(val_path, index=False)
    thr = _best_f1_threshold(vs[LABEL_COLUMN].to_numpy(), vs["prob"].to_numpy())

    results = []
    for t in pending:
        sp = own if t == man["dataset"] else load_splits(t, cfg, version)
        test = _sample(sp["test"], max_samples, cfg.seed)
        real = _sample(sp["test_realistic"], max_samples, cfg.seed)
        pt = scorer().score(test, f"teste {t}")
        pr = scorer().score(real, f"teste realista {t}")
        yt, yr = test[LABEL_COLUMN].to_numpy(), real[LABEL_COLUMN].to_numpy()
        gold = {}
        if "conferido" in test:
            g = (test["conferido"].fillna(0).astype(int) == 1).to_numpy()
            if g.any():
                gold = {"conferido_thrval": _metrics(yt[g], pt[g], thr), "n_conferido": int(g.sum())}
        res = {
            "run": run, "teste": t, "cruzado": t != man["dataset"], "parcial": bool(max_samples),
            "teste_hashes": data_fingerprint(t, version),
            "limiar_validacao": round(thr, 4),
            "n": {"teste": len(test), "phishing": int(yt.sum()), "realista": len(real)},
            "teste_thr0.5": _metrics(yt, pt, 0.5),
            "teste_thrval": _metrics(yt, pt, thr),
            "realista_thrval": _metrics(yr, pr, thr),
            **gold,
            "avaliado_em": datetime.now().isoformat(timespec="seconds"),
        }
        (evals / f"{t}.json").write_text(json.dumps(res, indent=1))
        if not max_samples:  # probabilidade de cada URL: base do exp stats (bootstrap, McNemar)
            _save_scores(run_dir / "scores" / f"{t}_teste.csv", test, pt)
            _save_scores(run_dir / "scores" / f"{t}_realista.csv", real, pr)
        errs = test.assign(prob_phishing=pt, pred=(pt >= thr).astype(int))
        errs = errs[errs.pred != errs[LABEL_COLUMN]]
        (run_dir / "errors").mkdir(exist_ok=True)
        errs[[URL_COLUMN, LABEL_COLUMN, "pred", "prob_phishing"]].to_csv(run_dir / "errors" / f"{t}.csv", index=False)
        m = res["teste_thrval"]
        print(f"[exp] {run} -> {t}: AP={m.get('average_precision')} F1={m['f1']} FPR={m['fpr']} (limiar {thr:.2f})")
        results.append(res)

    if need_op and not max_samples:
        if man["modelo"] != "xgb":
            print(f"[exp] {run}: medindo latencia em CPU (carrega o modelo na CPU; leva alguns minutos)")
        cpu = scorer() if man["modelo"] == "xgb" else _Scorer(man, run_dir, cfg, prefer_cpu=True)
        size = sum(f.stat().st_size for f in run_dir.rglob("*")
                   if f.is_file() and ("adapter" in f.parts or f.name == "model.json"))
        op = {"latencia_cpu_1url": cpu.latency(own["test"]), "tamanho_pesos_mb": round(size / 2**20, 2),
              "nota": "SLM: soma ao modelo base baixado do Hub; latencia sem a extracao das features"}
        (run_dir / "operational.json").write_text(json.dumps(op, indent=1))
    return results


# ---------------------------------------------------------------------------
# Matriz, status e leaderboard
# ---------------------------------------------------------------------------
def matrix(models=None, datasets=None, feature_sets=None) -> list[tuple[str, str, str]]:
    return [(m, d, f) for m in (models or MODELS) for d in (datasets or available())
            for f in (feature_sets or FEATURE_SET_NAMES)]


def status() -> pd.DataFrame:
    rows = []
    for m, d, f in matrix():
        rd = RUNS_DIR / run_name(m, d, f)
        man = _manifest(rd) or {}
        treino = man.get("status", "-")
        if treino == "concluido" and train_stale(man):
            treino = "desatualizado"
        evs = {}
        for t in DATASETS:
            ev = rd / "evals" / f"{t}.json"
            if not ev.exists():
                evs[f"eval:{t}"] = "-"
            else:
                evs[f"eval:{t}"] = "desatualizado" if eval_stale(json.loads(ev.read_text()), model_version(m)) else "ok"
        rows.append({"run": rd.name, "treino": treino, **evs})
    return pd.DataFrame(rows)


def leaderboard(cruzado: bool = False) -> pd.DataFrame:
    """Uma linha por (run, teste). Padrao: so o teste do PROPRIO dataset de treino
    (treina no BR, avalia no BR). ``cruzado`` inclui treino num, teste no outro."""
    rows = [dict(PAPER_PUBLISHED)]
    for ev in sorted(RUNS_DIR.glob("*/evals/*.json")):
        res = json.loads(ev.read_text())
        man = _manifest(ev.parent.parent)
        if not man or (res["teste"] != man["dataset"] and not cruzado):
            continue
        op_path = ev.parent.parent / "operational.json"
        op = json.loads(op_path.read_text()) if op_path.exists() else {}
        m, r = res["teste_thrval"], res["realista_thrval"]
        rows.append({
            "run": res["run"], "modelo": man["modelo"], "treino": man["dataset"], "features": man["features"],
            "teste": res["teste"] + (" (parcial)" if res.get("parcial") else ""),
            "n_features": len(man["feature_columns"]),
            "average_precision": m.get("average_precision"), "roc_auc": m.get("roc_auc"),
            "f1": m["f1"], "precision": m["precision"], "recall": m["recall"], "fpr": m["fpr"],
            "accuracy": m["accuracy"], "limiar": res["limiar_validacao"],
            "f1_realista": r["f1"], "precision_realista": r["precision"],
            "f1_conferido": (res.get("conferido_thrval") or {}).get("f1"),
            "n_conferido": res.get("n_conferido"),
            "lat_p95_ms": op.get("latencia_cpu_1url", {}).get("p95_ms"),
            "treino_s": (man.get("treino") or {}).get("train_seconds"),
        })
    df = pd.DataFrame(rows)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(LEADERBOARD_CSV, index=False)
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    body = "".join("| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |\n" for r in df.itertuples(index=False))
    LEADERBOARD_MD.write_text(
        "# Leaderboard\n\nMetricas no teste com o limiar de melhor F1 da validacao do dataset de treino. "
        "Particoes por dominio. A primeira linha e o numero publicado no artigo (particao aleatoria), "
        "so como referencia.\n\n" + head + body
    )
    return df
