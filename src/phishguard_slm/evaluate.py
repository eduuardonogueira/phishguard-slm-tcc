"""Funcoes de metrica usadas pela matriz de experimentos (experiments.py).

Inferencia linha a linha, metricas num limiar (acuracia, precisao, recall, F1,
ROC-AUC, matriz de confusao) e escolha do limiar de melhor F1 na validacao.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scoring import PhishClassifier


def _predict_frame(
    clf: PhishClassifier, df: pd.DataFrame, desc: str = "inferencia"
) -> pd.DataFrame:
    """Roda o classificador e devolve df com prob e latencia por linha."""
    from rich.progress import track

    probs, lats = [], []
    records = df.to_dict("records")
    for row in track(records, description=f"[eval] {desc} ({len(records)} URLs)"):
        pred = clf.predict_row(row)
        probs.append(pred.prob_phishing)
        lats.append(pred.latency_ms)
    out = df.copy()
    out["prob_phishing"] = probs
    out["latency_ms"] = lats
    return out


def _metrics_at(y_true: np.ndarray, probs: np.ndarray, thr: float) -> dict:
    y_pred = (probs >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    m = {
        "threshold": round(float(thr), 4),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }
    if len(np.unique(y_true)) > 1:
        m["roc_auc"] = round(float(roc_auc_score(y_true, probs)), 4)
    return m


def _best_f1_threshold(y_true: np.ndarray, probs: np.ndarray) -> float:
    best_thr, best_f1 = 0.5, -1.0
    for thr in np.linspace(0.05, 0.95, 19):
        f1 = f1_score(y_true, (probs >= thr).astype(int), zero_division=0)
        if f1 > best_f1:
            best_f1, best_thr = f1, float(thr)
    return best_thr
