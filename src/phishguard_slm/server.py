"""Servidor Flask que integra o SLM com a extensao de navegador.

Contrato da extensao (url-collector-extension/background.js):
  POST /receive_url  body: {"url": "..."}
  resposta: {"message": "<html curto>", "type": 0|1}
    type 0 -> pop-up verde  ("Navegacao Segura")
    type 1 -> pop-up vermelho ("Site Suspeito")

Endpoints do dashboard:
  GET /dashboard  -> HTML do dashboard (data-driven, modo ao vivo)
  GET /metrics    -> relatorios metrics_*.json (avaliacao)
  GET /stats      -> uso computacional ao vivo (latencia, RAM, CPU)
  GET /health     -> checagem simples
"""

from __future__ import annotations

import threading
import time
from collections import deque
from urllib.parse import urlparse

import numpy as np
import psutil
from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from .config import FEATURE_COLUMNS, ROOT, Config
from .features import extract_features
from .report import read_metrics
from .scoring import PhishClassifier

# Esquemas internos do navegador que nao devem ser classificados.
_SKIP_SCHEMES = {"chrome", "about", "edge", "brave", "chrome-extension", "devtools"}

DASHBOARD_HTML = ROOT / "src" / "pages" / "dashboard.html"


class _LiveStats:
    """Acumula estatisticas de uso computacional durante o serve."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lat = deque(maxlen=500)  # latencias recentes (ms)
        self._proc = psutil.Process()
        self.count = 0
        self.phishing = 0
        self.start = time.time()
        self._proc.cpu_percent(interval=None)  # inicializa o medidor

    def record(self, latency_ms: float, is_phish: bool) -> None:
        with self._lock:
            self._lat.append(latency_ms)
            self.count += 1
            if is_phish:
                self.phishing += 1

    def snapshot(self, device: str, threshold: float) -> dict:
        with self._lock:
            lats = list(self._lat)
            count, phishing = self.count, self.phishing
            uptime = time.time() - self.start
        arr = np.array(lats) if lats else np.array([])
        latency = {
            "n": int(arr.size),
            "p50_ms": round(float(np.percentile(arr, 50)), 1) if arr.size else None,
            "p95_ms": round(float(np.percentile(arr, 95)), 1) if arr.size else None,
            "mean_ms": round(float(arr.mean()), 1) if arr.size else None,
            "last_ms": round(float(arr[-1]), 1) if arr.size else None,
        }
        resource = {
            "process_rss_mb": round(self._proc.memory_info().rss / (1024 * 1024), 1),
            "cpu_percent": round(self._proc.cpu_percent(interval=None), 1),
        }
        return {
            "device": device,
            "threshold": threshold,
            "uptime_s": round(uptime, 1),
            "served": count,
            "phishing": phishing,
            "legit": count - phishing,
            "latency": latency,
            "resource": resource,
        }


def create_app(
    cfg: Config | None = None,
    use_adapter: bool = True,
    adapter_dir=None,
    feature_columns=FEATURE_COLUMNS,
) -> Flask:
    """``adapter_dir``/``feature_columns`` permitem servir um run da matriz
    (outputs/runs/<run>/adapter); o padrao e o adaptador de outputs/adapter com
    os 13 atributos, que e o integrado a extensao no TCC."""
    cfg = cfg or Config()
    app = Flask(__name__)
    CORS(app)

    print("[server] carregando classificador SLM...")
    clf = PhishClassifier(
        cfg,
        adapter_dir=(adapter_dir or cfg.adapter_dir) if use_adapter else None,
        prefer_cpu=True,
        feature_columns=feature_columns,
    )
    stats = _LiveStats()
    print(f"[server] pronto (device={clf.device}, adapter={use_adapter}).")

    @app.post("/receive_url")
    def receive_url():
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        # Features de DOM enviadas pela extensao (html_input, iframe, redirect).
        dom_features = data.get("features") or {}

        SAFE_MESSAGE = "&#9989; Navegacao Segura"

        if not url:
            return jsonify({"message": SAFE_MESSAGE, "type": 0})

        scheme = urlparse(url).scheme.lower()
        if scheme in _SKIP_SCHEMES:
            return jsonify({"message": SAFE_MESSAGE, "type": 0})

        # Modo unico: sempre reune URL (offline) + rede (WHOIS/TLS) + DOM do cliente.
        feats = extract_features(url)
        feats.update(
            {
                k: v
                for k, v in dom_features.items()
                if k in FEATURE_COLUMNS and v is not None
            }
        )
        # So os atributos com que o modelo foi treinado entram no prompt.
        feats = {k: v for k, v in feats.items() if v is not None and k in clf.feature_columns}

        print(feats)

        t0 = time.perf_counter()
        pred = clf.predict(url, features=feats)
        elapsed = (time.perf_counter() - t0) * 1000.0
        is_phish = pred.label == 1
        stats.record(elapsed, is_phish)

        prob_phishing_percent = f"{round(pred.prob_phishing * 100, 1)}%"

        SUSPECT_MESSAGE = (
            f"&#9888; Site Suspeito - possivel phishing! {prob_phishing_percent}"
        )

        print(
            f"[server] {url[:80]!r} -> P(phishing)={pred.prob_phishing:.3f} "
            f"type={int(is_phish)} ({elapsed:.0f} ms)"
        )
        return jsonify(
            {
                "message": SUSPECT_MESSAGE if is_phish else SAFE_MESSAGE,
                "type": 1 if is_phish else 0,
                "features_used": feats,
            }
        )

    @app.get("/stats")
    def get_stats():
        return jsonify(stats.snapshot(clf.device, cfg.threshold))

    @app.get("/metrics")
    def get_metrics():
        return jsonify({"metrics": read_metrics(cfg)})

    @app.get("/dashboard")
    @app.get("/")
    def dashboard():
        if not DASHBOARD_HTML.exists():
            return Response("dashboard.html nao encontrado", status=404)
        return Response(
            DASHBOARD_HTML.read_text(encoding="utf-8"), mimetype="text/html"
        )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "device": clf.device})

    return app


def serve(
    cfg: Config,
    use_adapter: bool = True,
    host: str = "127.0.0.1",
    port: int = 5000,
    adapter_dir=None,
    feature_columns=FEATURE_COLUMNS,
) -> None:
    app = create_app(cfg, use_adapter=use_adapter, adapter_dir=adapter_dir,
                     feature_columns=feature_columns)
    print(f"[server] dashboard em http://{host}:{port}/dashboard")
    app.run(host=host, port=port, debug=False)
