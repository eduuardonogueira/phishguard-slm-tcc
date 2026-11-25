"""Partida a frio e memória de pico (RSS) de um run, em CPU.

Mede, num processo novo:
  carga_s     tempo para carregar o modelo (base + adaptador LoRA, ou o XGBoost) em CPU
  primeira_ms latência da primeira URL (inclui aquecimento)
  rss_mb      pico de memória residente do processo após classificar ``--n`` URLs do teste
e grava ``outputs/runs/<run>/rss.json``.

Uso (um run por processo, para o RSS não se misturar):
  PHISHGUARD_LAT_THREADS=4 uv run python scripts/medir_rss.py qwen05b__br__url
"""

from __future__ import annotations

import json
import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1024 if sys.platform != "darwin" else r / 1024 / 1024  # Linux: KB; macOS: bytes


def main() -> None:
    run = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    run_dir = ROOT / "outputs" / "runs" / run
    man = json.loads((run_dir / "manifest.json").read_text())
    from phishguard_slm.config import Config
    from phishguard_slm.experiments import load_splits

    test = load_splits(man["dataset"])["test"].head(n)
    base = rss_mb()
    t0 = time.perf_counter()
    if man["modelo"] == "xgb":
        from xgboost import XGBClassifier

        clf = XGBClassifier(); clf.load_model(run_dir / "model.json")
        cols = man["feature_columns"]
        score = lambda row: clf.predict_proba(row[cols].astype(float).to_frame().T)
    else:
        import torch

        torch.set_num_threads(int(os.environ.get("PHISHGUARD_LAT_THREADS", "4")))
        from phishguard_slm.scoring import PhishClassifier

        cfg = Config(); cfg.model_id = man["model_id"]
        clf = PhishClassifier(cfg, adapter_dir=run_dir / "adapter", prefer_cpu=True,
                              feature_columns=man["feature_columns"])
        score = lambda row: clf.predict_row(row.to_dict())
    carga = time.perf_counter() - t0
    t1 = time.perf_counter(); score(test.iloc[0]); primeira = (time.perf_counter() - t1) * 1000
    for i in range(1, len(test)):
        score(test.iloc[i])
    out = {"run": run, "carga_s": round(carga, 2), "primeira_ms": round(primeira, 1),
           "rss_mb": round(rss_mb(), 1), "rss_antes_do_modelo_mb": round(base, 1), "n": len(test),
           "threads": os.environ.get("PHISHGUARD_LAT_THREADS", "4")}
    (run_dir / "rss.json").write_text(json.dumps(out, indent=1))
    print(out)


if __name__ == "__main__":
    main()
