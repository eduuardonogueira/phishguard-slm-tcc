"""Carregamento do dataset e construcao dos splits.

Evita o erro do baseline (so um split aleatorio 85/15): produz splits
estratificados train/val/test com semente fixa e um conjunto de teste em
"proporcao realista" (phishing como minoria) para medir precisao/recall sob
trafego realista.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

from .config import LABEL_COLUMN, URL_COLUMN, Config


@dataclass
class Splits:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    test_realistic: pd.DataFrame

    def summary(self) -> dict[str, dict[str, int]]:
        def counts(df: pd.DataFrame) -> dict[str, int]:
            n1 = int((df[LABEL_COLUMN] == 1).sum())
            n0 = int((df[LABEL_COLUMN] == 0).sum())
            return {"total": len(df), "phishing": n1, "legit": n0}

        return {
            "train": counts(self.train),
            "val": counts(self.val),
            "test": counts(self.test),
            "test_realistic": counts(self.test_realistic),
        }


def load_dataset(csv_path: Path) -> pd.DataFrame:
    """Le o CSV mantendo URL + rotulo + todas as features, limpando linhas invalidas.

    Diferente do baseline (que usava apenas ``url`` e ``phishing``), agora
    preservamos todas as colunas de features do dataset para que sejam usadas
    como atributos no prompt do SLM.
    """
    df = pd.read_csv(csv_path)
    if URL_COLUMN not in df.columns or LABEL_COLUMN not in df.columns:
        raise ValueError(
            f"CSV precisa conter as colunas '{URL_COLUMN}' e '{LABEL_COLUMN}'; "
            f"encontradas: {list(df.columns)}"
        )
    df = df.dropna(subset=[URL_COLUMN, LABEL_COLUMN])
    df[URL_COLUMN] = df[URL_COLUMN].astype(str).str.strip()
    df = df[df[URL_COLUMN] != ""]
    df[LABEL_COLUMN] = df[LABEL_COLUMN].astype(int)
    df = df.drop_duplicates(subset=[URL_COLUMN]).reset_index(drop=True)
    return df


def make_realistic_test(test: pd.DataFrame, phishing_rate: float, seed: int) -> pd.DataFrame:
    """Reamostra o test para que phishing seja minoria (~5-10%).

    Subamostra a classe phishing mantendo todos os legitimos, atingindo a taxa
    alvo. Reflete o trafego real, onde phishing e raro.
    """
    legit = test[test[LABEL_COLUMN] == 0]
    phish = test[test[LABEL_COLUMN] == 1]
    if len(legit) == 0 or len(phish) == 0:
        return test.copy()

    # phishing_rate = n_phish / (n_phish + n_legit)  =>  n_phish alvo
    target_phish = int(round(phishing_rate * len(legit) / (1 - phishing_rate)))
    target_phish = max(1, min(target_phish, len(phish)))
    phish_sampled = phish.sample(n=target_phish, random_state=seed)
    out = pd.concat([legit, phish_sampled], ignore_index=True)
    return out.sample(frac=1.0, random_state=seed).reset_index(drop=True)


def build_splits(cfg: Config) -> Splits:
    """Constroi splits estratificados a partir do dataset configurado."""
    df = load_dataset(cfg.dataset_csv)

    # test primeiro (estratificado), depois val a partir do restante.
    train_val, test = train_test_split(
        df,
        test_size=cfg.test_size,
        stratify=df[LABEL_COLUMN],
        random_state=cfg.seed,
    )
    val_frac = cfg.val_size / (1.0 - cfg.test_size)
    train, val = train_test_split(
        train_val,
        test_size=val_frac,
        stratify=train_val[LABEL_COLUMN],
        random_state=cfg.seed,
    )

    test_realistic = make_realistic_test(test, cfg.realistic_phishing_rate, cfg.seed)

    return Splits(
        train=train.reset_index(drop=True),
        val=val.reset_index(drop=True),
        test=test.reset_index(drop=True),
        test_realistic=test_realistic,
    )


def load_external_test(cfg: Config) -> pd.DataFrame | None:
    """Carrega dataset externo (cross-dataset) se ``external_csv`` estiver setado."""
    if cfg.external_csv is None:
        return None
    return load_dataset(Path(cfg.external_csv))
