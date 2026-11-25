"""Obtenção e preparação dos dois conjuntos de dados usados no TCC.

trabalho-base (``paper``)
    CSV publicado no repositório do Phishing Guardian (Guarizi; Mascarenhas; Moraes, 2025),
    baixado num commit fixo e conferido pelo SHA-256. Não é redistribuído aqui.

PhishBR-URL (``br``)
    Versão 1 publicada no Kaggle (DOI 10.34740/KAGGLE/DSV/22753851, CC BY-SA 4.0), baixada
    com o ``kagglehub`` e conferida pelo SHA-256. Já traz a partição usada no TCC (coluna
    ``split``), que é congelada em ``datasets/splits/br.csv``.

Diferenças em relação aos dados usados no TCC, todas no conjunto BR:
  * 306 URLs tiveram dados pessoais mascarados na publicação (e-mails, números no formato
    de CPF, valores de parâmetros sensíveis), com o mesmo comprimento. Os atributos não
    mudam, mas o texto da URL lido pelos SLMs muda nessas linhas.
  * Duas linhas de treino ficaram com URL idêntica a outra após o mascaramento. Como a
    URL é a chave da partição, a cópia é descartada aqui (26.722 linhas, 18.751 no treino).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import LABEL_COLUMN, ROOT, URL_COLUMN

PAPER_COMMIT = "d520a9a44ad13ca28819afb5351a9e818bc33d6a"
PAPER_URL = (
    "https://raw.githubusercontent.com/bguarizi/phishing-guardian/"
    f"{PAPER_COMMIT}/data_bases/data_base.csv"
)
PAPER_SHA256 = "047881b8abcd7218f8279778ee0e95a27dfac7f9d982eff33841888822a516f5"

BR_HANDLE = "eduuardonog/phishbr-url/versions/1"
BR_FILE = "phishbr_url.csv"
BR_SHA256 = "b442b7d6c42b3f45cc936f48ca5c820bb2bdd32f6656e6958691e059eacdd3e1"
BR_DOI = "10.34740/KAGGLE/DSV/22753851"

DATASETS_DIR = ROOT / "datasets"
SPLITS_DIR = DATASETS_DIR / "splits"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _conferir(path: Path, esperado: str) -> None:
    obtido = _sha256(path)
    if obtido != esperado:
        raise RuntimeError(f"{path.name}: SHA-256 {obtido} difere do esperado {esperado}")


def baixar_paper(force: bool = False) -> Path:
    """datasets/paper/dataset_normalizado.csv: o CSV original do trabalho-base."""
    out = DATASETS_DIR / "paper" / "dataset_normalizado.csv"
    if out.exists() and not force:
        _conferir(out, PAPER_SHA256)
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with urllib.request.urlopen(PAPER_URL, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    _conferir(tmp, PAPER_SHA256)
    tmp.replace(out)
    return out


def baixar_br(force: bool = False) -> Path:
    """Baixa o PhishBR-URL (versão 1) do Kaggle; não exige conta para dataset público."""
    import kagglehub

    pasta = Path(kagglehub.dataset_download(BR_HANDLE, force_download=force))
    path = pasta / BR_FILE
    _conferir(path, BR_SHA256)
    return path


def preparar_br(origem: Path) -> dict:
    """Grava datasets/br/dataset.csv e congela a partição publicada em splits/br.csv."""
    df = pd.read_csv(origem, low_memory=False)
    antes = len(df)
    df = df.drop_duplicates(subset=[URL_COLUMN], keep="first").reset_index(drop=True)
    descartadas = antes - len(df)

    out = DATASETS_DIR / "br" / "dataset.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.drop(columns="split").to_csv(out, index=False)

    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    df[[URL_COLUMN, "split"]].to_csv(SPLITS_DIR / "br.csv", index=False)
    return {"linhas": len(df), "duplicadas_descartadas": descartadas}


def _meta_particao(nome: str, origem_particao: str) -> dict:
    """Recria splits/<nome>.json (hashes e contagens) para a partição congelada."""
    from .experiments import DATASETS

    df = pd.read_csv(DATASETS[nome]["bruto"], low_memory=False)
    sp = pd.read_csv(SPLITS_DIR / f"{nome}.csv")
    df = df.merge(sp, on=URL_COLUMN, how="inner", validate="one_to_one")
    if len(df) != len(sp):
        raise RuntimeError(f"{nome}: {len(df)} linhas casam com a partição de {len(sp)}")
    grupo = df["dominio"].fillna(df[URL_COLUMN])
    df = df.assign(grupo=grupo)
    meta = {
        "dataset": nome,
        "dataset_sha256": _sha256(DATASETS[nome]["bruto"]),
        "splits_sha256": _sha256(SPLITS_DIR / f"{nome}.csv"),
        "seed": 42,
        "origem_particao": origem_particao,
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "contagem": {
            s: {"total": int((df.split == s).sum()),
                "phishing": int(df[df.split == s][LABEL_COLUMN].sum()),
                "dominios": int(df[df.split == s].grupo.nunique())}
            for s in ("train", "val", "test")
        },
        "dominios_em_mais_de_um_split": int((df.groupby("grupo").split.nunique() > 1).sum()),
    }
    if "conferido" in df:
        meta["conferidas_no_teste"] = int(df[df.split == "test"]["conferido"].fillna(0).sum())
    (SPLITS_DIR / f"{nome}.json").write_text(json.dumps(meta, indent=1))
    return meta


def preparar(force: bool = False) -> dict:
    """Baixa, confere e prepara os dois conjuntos; recria os metadados das partições."""
    from .experiments import build_paper_dataset, normalize_br

    baixar_paper(force)
    paper = build_paper_dataset()
    br = preparar_br(baixar_br(force))
    normalize_br()
    return {
        "paper": {"linhas": paper["linhas"], "phishing": paper["phishing"],
                  "particao": _meta_particao("paper", "datasets/splits/paper.csv (versionada)")},
        "br": {**br, "doi": BR_DOI,
               "particao": _meta_particao("br", f"coluna split do Kaggle ({BR_HANDLE})")},
    }
