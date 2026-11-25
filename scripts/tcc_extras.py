"""Complementos do TCC calculados SÓ a partir dos scores salvos (nenhum modelo é carregado).

Para cada run de um dataset (padrão: br), lê ``outputs/runs/*/scores/<d>_teste.csv`` e grava:

  outputs/stats/<d>_extras.csv   precisão nas prevalências de 0,1%, 1% e 7% (TPR e FPR no limiar
                                 da validação, IC 95% por bootstrap de domínio), Brier, FPR sem
                                 os 2 CDNs de anúncio (2mdn.net, brandcdn.com)
  outputs/figuras/<d>_pr.png     curvas precisão-revocação
  outputs/figuras/<d>_ap_latencia.png   AP (IC 95%) x latência p50 em CPU (escala log)
  outputs/figuras/<d>_calibracao.png    curva de confiabilidade (10 faixas)

Precisão numa prevalência π, a partir de TPR e FPR medidos no teste:
    P(π) = TPR·π / (TPR·π + FPR·(1−π))
É a mesma correção de taxa-base de Axelsson (2000); supõe que TPR e FPR não mudam com π.

Uso:  uv run --with matplotlib python scripts/tcc_extras.py [--dataset br] [--boot 2000]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from phishguard_slm.stats import average_precision, at_threshold, cluster_indices, load_runs

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "outputs" / "runs"
PREVS = (0.001, 0.01, 0.07)
CDNS = ("2mdn.net", "brandcdn.com")
NOMES = {"qwen05b": "Qwen2.5-0.5B + LoRA", "gemma1b": "Gemma 3 1B + LoRA", "xgb": "XGBoost"}
CORES = {"qwen05b": "#1b6ca8", "gemma1b": "#c4572a", "xgb": "#5b5b5b"}
ESTILO = {"todas": "-", "corr": "--", "url": ":"}
MARCA = {"todas": "o", "corr": "s", "url": "^"}


def prec_at(tpr: float, fpr: float, pi: float) -> float:
    den = tpr * pi + fpr * (1 - pi)
    return tpr * pi / den if den else float("nan")


def groups_for(dataset: str) -> dict[str, str]:
    df = pd.read_csv(ROOT / "datasets" / dataset / "dataset_normalizado.csv",
                     usecols=lambda c: c in {"url", "dominio"})
    if "dominio" not in df:
        from phishguard_slm.dominios import domain_info

        df["dominio"] = df.url.map(lambda u: domain_info(u)["reg_domain"])
    return dict(zip(df.url, df.dominio.fillna(df.url)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="br")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    d = a.dataset
    runs, missing = load_runs(RUNS, d)
    if missing:
        print("sem scores:", missing)
    g = groups_for(d)
    rng = np.random.default_rng(a.seed)
    rows, curves = [], {}
    for r in runs:
        t = r.test
        y, p = t["phishing"].to_numpy(int), t["prob"].to_numpy(float)
        dom = t["url"].map(g).fillna(t["url"]).to_numpy()
        m = at_threshold(y, p, r.thr)
        tpr, fpr = m["recall"], m["fpr"]
        boots = cluster_indices(dom, a.boot, rng)
        bp = {pi: [] for pi in PREVS}
        for idx in boots:
            mb = at_threshold(y[idx], p[idx], r.thr)
            for pi in PREVS:
                bp[pi].append(prec_at(mb["recall"], mb["fpr"], pi))
        keep = ~np.isin(dom, CDNS)
        m_sem = at_threshold(y[keep], p[keep], r.thr)
        op = json.loads((RUNS / r.name / "operational.json").read_text())
        lat = op.get("latencia_cpu_1url", {})
        row = {"run": r.name, "modelo": r.model, "features": r.features, "limiar_val": r.thr,
               "ap": average_precision(y, p), "tpr": tpr, "fpr": fpr,
               "brier": float(np.mean((p - y) ** 2)),
               "fpr_sem_cdns": m_sem["fpr"], "n_cdns": int((~keep).sum()),
               "lat_p50_ms": lat.get("p50_ms"), "lat_p95_ms": lat.get("p95_ms"),
               "tamanho_mb": op.get("tamanho_pesos_mb")}
        for pi in PREVS:
            lo, hi = np.nanpercentile(bp[pi], [2.5, 97.5])
            row[f"prec_{pi:g}"] = prec_at(tpr, fpr, pi)
            row[f"prec_{pi:g}_ic_inf"], row[f"prec_{pi:g}_ic_sup"] = float(lo), float(hi)
        rows.append(row)
        order = np.argsort(-p, kind="mergesort")
        tps = np.cumsum(y[order]); fps = np.cumsum(1 - y[order])
        curves[r.name] = (tps / y.sum(), tps / (tps + fps), y, p)
    out = pd.DataFrame(rows).sort_values("ap", ascending=False)
    stats_dir = ROOT / "outputs" / "stats"
    out.round(5).to_csv(stats_dir / f"{d}_extras.csv", index=False)
    print(out[["run", "ap", "brier", "fpr", "fpr_sem_cdns", "prec_0.001", "prec_0.01", "prec_0.07"]]
          .round(4).to_string(index=False))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = ROOT / "outputs" / "figuras"
    fig_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "font.family": "DejaVu Sans"})

    # Curvas PR
    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    for r in sorted(runs, key=lambda r: (r.model, r.features)):
        rec, prec, _, _ = curves[r.name]
        ax.plot(rec, prec, ESTILO[r.features], color=CORES[r.model], lw=1.3,
                label=f"{NOMES[r.model]} – {r.features}")
    base = runs[0].test["phishing"].mean()
    ax.axhline(base, color="#999", lw=0.8, ls="-.")
    ax.text(0.01, base + 0.01, f"prevalência do teste ({base:.0%})".replace(".", ","), fontsize=8, color="#666")
    ax.set_xlabel("Revocação"); ax.set_ylabel("Precisão"); ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.3); ax.legend(fontsize=7, loc="lower left", ncol=1)
    fig.tight_layout(); fig.savefig(fig_dir / f"{d}_pr.png", dpi=200); plt.close(fig)

    # AP x latência
    st = pd.read_csv(stats_dir / f"{d}_runs.csv").set_index("run")
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    for _, row in out.iterrows():
        s = st.loc[row.run]
        ax.errorbar(row.lat_p50_ms, s.ap, yerr=[[s.ap - s.ap_ic_inf], [s.ap_ic_sup - s.ap]],
                    fmt=MARCA[row.features], color=CORES[row.modelo], ms=6, capsize=2, lw=1)
    for m, c in CORES.items():
        ax.plot([], [], "o", color=c, label=NOMES[m])
    for f, mk in MARCA.items():
        ax.plot([], [], mk, color="#333", mfc="none", label=f"atributos: {f}")
    ax.set_xscale("log"); ax.set_xlabel("Latência p50 em CPU, 4 threads (ms, escala log)")
    ax.set_ylabel("AP no teste (IC 95%)"); ax.grid(alpha=0.3, which="both"); ax.legend(fontsize=7, loc="lower right")
    fig.tight_layout(); fig.savefig(fig_dir / f"{d}_ap_latencia.png", dpi=200); plt.close(fig)

    # Calibração
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    bins = np.linspace(0, 1, 11)
    for r in [r for r in runs if r.features == "todas"]:
        _, _, y, p = curves[r.name]
        k = np.clip(np.digitize(p, bins) - 1, 0, 9)
        xs = [p[k == b].mean() for b in range(10) if (k == b).sum() >= 10]
        ys = [y[k == b].mean() for b in range(10) if (k == b).sum() >= 10]
        ax.plot(xs, ys, "o-", color=CORES[r.model], lw=1.2, ms=4, label=f"{NOMES[r.model]} – todas")
    ax.plot([0, 1], [0, 1], color="#999", lw=0.8, ls="--", label="calibração perfeita")
    ax.set_xlabel("Probabilidade prevista de phishing"); ax.set_ylabel("Fração observada de phishing")
    ax.grid(alpha=0.3); ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout(); fig.savefig(fig_dir / f"{d}_calibracao.png", dpi=200); plt.close(fig)
    print("figuras em", fig_dir.relative_to(ROOT))


if __name__ == "__main__":
    main()
