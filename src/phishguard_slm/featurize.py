"""Definicao unica das 13 features do Phishing Guardian (paper), em unidades legiveis.

O CSV original do paper (``datasets/paper/dataset_normalizado.csv``) traz as features normalizadas por
divisores fixos. Os divisores foram inferidos dos dados e conferidos com dominios
de data de criacao conhecida (google.com, facebook.com, github.com):

  url_lenght     = caracteres / 10.000
  dot_count      = pontos / 100
  activate_days  = dias desde a criacao do dominio / 40.000 (referencia ~30/04/2024;
                   0 = consulta WHOIS falhou, 61% das linhas)
  certificate    = validade do certificado (notAfter - notBefore) em dias / 730;
                   0 sem HTTPS (90 dias do Let's Encrypt = 0,1233, o valor mais comum)
  page_rank      = Open PageRank (0-10) / 10; 0 = dominio nao encontrado

Os datasets deste trabalho guardam as unidades originais (caracteres, dias,
0-10), que o SLM le melhor no prompt. Para o XGBoost a escala e indiferente.

As definicoes lexicas abaixo reproduzem as colunas do paper; a concordancia com o
CSV original e medida por ``lexical_agreement`` (o artigo descreve A5 como
"contem @" e A10 como "contem //").
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit

from .config import FEATURE_COLUMNS

LEXICAL = (
    "url_lenght",
    "is_https",
    "ip_format",
    "dot_count",
    "suspect_char",
    "caract_hifen",
    "https_text",
    "redirect",
)
DOM = ("html_input", "iframe")
NETWORK = ("activate_days", "certificate", "page_rank")
assert set(LEXICAL + DOM + NETWORK) == set(FEATURE_COLUMNS)

# Divisor que leva a unidade legivel para a escala do CSV do paper.
PAPER_SCALE = {
    "url_lenght": 10_000,
    "dot_count": 100,
    "activate_days": 40_000,
    "certificate": 730,
    "page_rank": 10,
}


def _host_is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def lexical(url: str) -> dict[str, int]:
    """As 8 features derivadas so da string da URL."""
    try:
        parts = urlsplit(url)
        host, netloc = parts.hostname or "", parts.netloc
        scheme = parts.scheme.lower()
    except ValueError:
        host, netloc, scheme = "", "", url.split(":", 1)[0].lower()
    rest = url.split("://", 1)[-1]
    return {
        "url_lenght": len(url),
        "is_https": int(scheme == "https"),
        "ip_format": int(_host_is_ip(host)),
        "dot_count": url.count("."),
        "suspect_char": int("@" in url),
        "caract_hifen": int("-" in netloc),
        "https_text": int("https" in rest.lower()),
        "redirect": int("//" in rest),
    }


_RE_INPUT = re.compile(rb"<input\b", re.I)
_RE_IFRAME = re.compile(rb"<iframe\b", re.I)


def dom(html: bytes | str) -> dict[str, int]:
    """html_input e iframe a partir do HTML da pagina."""
    if isinstance(html, str):
        html = html.encode("utf-8", "replace")
    return {
        "html_input": int(bool(_RE_INPUT.search(html))),
        "iframe": int(bool(_RE_IFRAME.search(html))),
    }


def from_paper_scale(df):
    """Converte as colunas do CSV do paper para as unidades legiveis."""
    out = df.copy()
    for col, div in PAPER_SCALE.items():
        vals = out[col].astype(float) * div
        out[col] = vals.round(0 if col != "page_rank" else 2)
    for col in ("url_lenght", "dot_count", "activate_days", "certificate"):
        out[col] = out[col].astype("Int64")
    return out


def to_paper_scale(df):
    """Caminho inverso: unidades legiveis -> escala do CSV do paper (para os modelos de ML).

    Usa os MESMOS divisores do paper (nao min-max do proprio dataset), para que um
    modelo treinado num dataset receba os numeros na mesma escala ao ser testado no
    outro. Valores vazios continuam vazios (o XGBoost trata NaN nativamente).
    """
    out = df.copy()
    for col, div in PAPER_SCALE.items():
        out[col] = out[col].astype(float) / div
    return out


def lexical_agreement(df) -> dict[str, Any]:
    """Fracao de linhas em que ``lexical`` reproduz a coluna do paper."""
    import pandas as pd

    ours = pd.DataFrame([lexical(u) for u in df["url"]], index=df.index)
    res = {}
    for col in LEXICAL:
        a, b = ours[col].astype(float), df[col].astype(float)
        diff = a != b
        res[col] = {
            "concordancia": round(float(1 - diff.mean()), 4),
            "divergentes": int(diff.sum()),
            "paper_1_nosso_0": int(((b > 0) & (a == 0)).sum()) if col not in ("url_lenght", "dot_count") else None,
        }
    return res
