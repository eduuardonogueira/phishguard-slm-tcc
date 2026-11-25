"""Erros por fonte de origem e concentração dos falsos negativos no teste BR.

Só lê os scores salvos (``outputs/runs/*/scores/br_teste.csv``) e o dataset BR; nenhum modelo é
carregado. No limiar da validação de cada run, grava em ``outputs/stats/``:

  br_por_fonte.csv   por (run, classe, fonte): n, domínios, erros e taxa de erro
                     (FPR nas legítimas, 1 − revocação no phishing), com IC 95% por bootstrap
                     de domínios dentro da fonte
  br_sufixo.csv      por run: revocação no phishing e FPR nas legítimas, separadas por sufixo
                     .br e não-.br (com e sem os 2 CDNs de anúncio), e FPR das legítimas do
                     PhreshPhish sem os CDNs
  br_fn_dominios.csv por run: falsos negativos, domínios com FN, % nos 5 maiores, 5 maiores,
                     e FN por sufixo (.br ou não) e por hospedagem compartilhada

Uso: uv run python scripts/tcc_erros.py [--boot 2000]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from phishguard_slm.stats import cluster_indices, load_runs

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "outputs" / "runs"
SHARED = (r"(?:blogspot|weebly|wixsite|000webhost|firebaseapp|web\.app|pages\.dev|github\.io|sites\.google|"
          r"netlify|vercel\.app|glitch\.me|workers\.dev|square\.site|godaddysites|webflow\.io)")
RUNS_SEL = ("qwen05b__br__todas", "qwen05b__br__url", "gemma1b__br__todas", "xgb__br__todas", "xgb__br__url")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    ds = pd.read_csv(ROOT / "datasets" / "br" / "dataset_normalizado.csv",
                     usecols=["url", "dominio", "origem"])
    ds["fonte"] = ds.origem.str.replace("-n96ncsr5g4", "", regex=False)
    meta = ds.drop_duplicates("url").set_index("url")
    runs, _ = load_runs(RUNS, "br")
    rng = np.random.default_rng(a.seed)
    rows, fn_rows, suf_rows = [], [], []
    for r in [r for r in runs if r.name in RUNS_SEL]:
        t = r.test.join(meta, on="url")
        t["dominio"] = t.dominio.fillna(t.url)
        pred = t.prob.to_numpy() >= r.thr
        y = t.phishing.to_numpy(int)
        t["erro"] = pred != (y == 1)
        for (cls, fonte), g in t.groupby(["phishing", "fonte"]):
            if len(g) < 20:
                continue
            e = g.erro.to_numpy(float)
            idx = cluster_indices(g.dominio.to_numpy(), a.boot, rng)
            bs = [e[i].mean() for i in idx]
            lo, hi = np.percentile(bs, [2.5, 97.5])
            rows.append({"run": r.name, "classe": "phishing" if cls else "legitima", "fonte": fonte,
                         "n": len(g), "dominios": g.dominio.nunique(), "erros": int(e.sum()),
                         "taxa_erro": e.mean(), "ic_inf": lo, "ic_sup": hi})
        br = t.dominio.str.endswith(".br").to_numpy()
        cdn = t.dominio.isin(["2mdn.net", "brandcdn.com"]).to_numpy()
        ph, lg = y == 1, y == 0
        rate = lambda m: float(pred[m].mean()) if m.any() else float("nan")
        phl = lg & (t.fonte == "phreshphish").to_numpy() & ~cdn
        suf_rows.append({"run": r.name,
                         "n_phish_br": int((ph & br).sum()), "recall_phish_br": rate(ph & br),
                         "n_phish_nao_br": int((ph & ~br).sum()), "recall_phish_nao_br": rate(ph & ~br),
                         "n_legit_br": int((lg & br).sum()), "fpr_legit_br": rate(lg & br),
                         "n_legit_nao_br": int((lg & ~br).sum()), "fpr_legit_nao_br": rate(lg & ~br),
                         "fpr_legit_nao_br_sem_cdns": rate(lg & ~br & ~cdn),
                         "n_legit_phreshphish_sem_cdns": int(phl.sum()), "fpr_legit_phreshphish_sem_cdns": rate(phl)})
        fn = t[(y == 1) & ~pred]
        top = fn.dominio.value_counts()
        allp = t[y == 1]
        fn_rows.append({"run": r.name, "fn": len(fn), "dominios_fn": fn.dominio.nunique(),
                        "pct_top5": top.head(5).sum() / max(len(fn), 1),
                        "top5": ", ".join(f"{d} ({n})" for d, n in top.head(5).items()),
                        "fn_sufixo_br": float(fn.dominio.str.endswith(".br").mean()),
                        "phish_sufixo_br": float(allp.dominio.str.endswith(".br").mean()),
                        "fn_hospedagem_compartilhada": float(fn.url.str.contains(SHARED, regex=True).mean()),
                        "phish_hospedagem_compartilhada": float(allp.url.str.contains(SHARED, regex=True).mean())})
    out = pd.DataFrame(rows)
    out.round(4).to_csv(ROOT / "outputs" / "stats" / "br_por_fonte.csv", index=False)
    fnd = pd.DataFrame(fn_rows)
    fnd.round(4).to_csv(ROOT / "outputs" / "stats" / "br_fn_dominios.csv", index=False)
    suf = pd.DataFrame(suf_rows)
    suf.round(4).to_csv(ROOT / "outputs" / "stats" / "br_sufixo.csv", index=False)
    pd.set_option("display.width", 200)
    print(suf.round(3).to_string(index=False))
    print(out.round(3).to_string(index=False))
    print(fnd.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
