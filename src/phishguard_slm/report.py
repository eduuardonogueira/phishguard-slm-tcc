"""Geracao do dashboard de metricas (HTML).

Le os relatorios ``metrics_*.json`` do diretorio de reports e produz uma
versao *standalone* do dashboard, com os dados embutidos, que abre offline
(sem servidor) e pode ser versionada / publicada (ex.: GitHub Pages).

O mesmo arquivo ``src/pages/dashboard.html`` e usado tanto aqui (embutindo
dados) quanto pelo servidor Flask (modo ao vivo, buscando /metrics e /stats).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import ROOT, Config

DASHBOARD_TEMPLATE = ROOT / "src" / "pages" / "dashboard.html"
_DATA_PLACEHOLDER = (
    '<script id="pg-data" type="application/json">null</script>'
)


def read_metrics(cfg: Config) -> dict:
    """Le os relatorios de metricas disponiveis (finetuned / zeroshot)."""
    out: dict = {}
    for tag in ("finetuned", "zeroshot"):
        path = cfg.reports_dir / f"metrics_{tag}.json"
        out[tag] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return out


def generate_report(cfg: Config, out_path: Path | None = None) -> Path:
    """Gera o dashboard standalone com os dados embutidos.

    Retorna o caminho do HTML gerado (default: ``outputs/reports/dashboard.html``).
    """
    if not DASHBOARD_TEMPLATE.exists():
        raise FileNotFoundError(f"template nao encontrado: {DASHBOARD_TEMPLATE}")

    metrics = read_metrics(cfg)
    if not any(metrics.values()):
        raise FileNotFoundError(
            "nenhum metrics_*.json encontrado em "
            f"{cfg.reports_dir} — rode `phishguard eval` primeiro."
        )

    payload = {
        "metrics": metrics,
        "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    injected = (
        '<script id="pg-data" type="application/json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script>"
    )

    template = DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    html = template.replace(_DATA_PLACEHOLDER, injected)

    out_path = out_path or (cfg.reports_dir / "dashboard.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
