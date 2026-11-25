"""Extracao de features em tempo de inferencia (runtime), fora do dataset.

O dataset traz as features pre-computadas, mas na inferencia ao vivo (extensao/
servidor) so chega a URL. Este modulo reconstroi as features a partir da URL e de
consultas de rede (WHOIS, TLS, PageRank).

Guiado por ``FEATURE_COLUMNS`` (config): so calcula as features configuradas para
o treino. Assim, remover uma feature de ``FEATURE_COLUMNS`` a remove tanto do
treino quanto do que a extensao envia ao modelo -- e evita a consulta de rede
cara correspondente (WHOIS/TLS/API).

Grupos:
  - features de URL (sem rede): derivam da string da URL.
  - features de rede (com rede): WHOIS (activate_days), TLS (certificate) e
    Open PageRank (page_rank). Falhas retornam ``None`` (o prompt omite).

As features de DOM (html_input, iframe, redirect) NAO sao computadas aqui: vem do
navegador (extensao) via corpo da requisicao, pois exigem a pagina renderizada.

Aviso de calibracao: as definicoes exatas usadas para gerar o dataset original
sao desconhecidas; estas extracoes sao aproximacoes razoaveis e podem divergir da
distribuicao de treino.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import ssl
import socket
import sys
import urllib.request
import requests
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import quote, urlsplit

from .config import FEATURE_COLUMNS

# Caracteres tipicamente associados a URLs suspeitas/ofuscadas.
_SUSPECT_CHARS = re.compile(r"[@%]")


def _host_is_ip(host: str) -> bool:
    """True se o host for um endereco IP (v4 ou v6), nao um dominio."""
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def extract_url_features(
    url: str, columns: Iterable[str] = FEATURE_COLUMNS
) -> dict[str, Any]:
    """Features derivaveis apenas da string da URL (sem rede, sem DOM).

    Retorna apenas as chaves presentes em ``columns`` (default: FEATURE_COLUMNS),
    com inteiros para contagens e 0/1 para binarias.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    # Resto da URL sem o scheme (para detectar "https" no texto/host/path).
    rest = url.split("://", 1)[-1].lower()

    all_feats = {
        "url_lenght": len(url),
        "is_https": 1 if parts.scheme.lower() == "https" else 0,
        "ip_format": 1 if _host_is_ip(host) else 0,
        "dot_count": url.count("."),
        "suspect_char": 1 if _SUSPECT_CHARS.search(url) else 0,
        "caract_hifen": 1 if "-" in url else 0,
        "https_text": 1 if "https" in rest else 0,
    }
    cols = set(columns)
    return {k: v for k, v in all_feats.items() if k in cols}


def _whois_activate_days(host: str, timeout: float) -> int | None:
    """Idade do dominio em dias via WHOIS. None em falha/indisponivel."""
    try:
        import whois  # python-whois (import tardio: dep opcional do modo completo)

        socket.setdefaulttimeout(timeout)
        data = whois.whois(host)
        created = data.creation_date if data else None
        if isinstance(created, list):
            created = created[0] if created else None
        if not isinstance(created, datetime):
            return None
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - created).days
        return days if days >= 0 else None
    except Exception:
        return None
    finally:
        socket.setdefaulttimeout(None)


def _tls_certificate_days(host: str, timeout: float) -> int | None:
    """Janela de validade do certificado TLS em dias (notAfter - notBefore).

    None quando nao ha HTTPS/certificado ou a conexao falha. Observacao: este
    valor nao se alinha aos valores (corrompidos) da coluna ``certificate`` do
    dataset paper; serve como sinal de certificado ate um re-featurization limpo.
    """
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        if not cert:
            return None
        not_before = ssl.cert_time_to_seconds(cert["notBefore"])
        not_after = ssl.cert_time_to_seconds(cert["notAfter"])
        return int((not_after - not_before) / 86400)
    except Exception:
        return None


_PR_WARNED = False


_OPENPAGERANK_URL = "https://openpagerank.keywordseverywhere.com/v1/domains/bulk"


def _open_pagerank(host: str, timeout: float) -> float | None:
    """PageRank do dominio via Open PageRank API (normalizado 0-10 -> 0-1).

    Requer a variavel de ambiente ``OPENPAGERANK_API_KEY`` (token Bearer). POST em
    ``/v1/domains/bulk`` com o dominio; le ``open_page_rank`` (0-10) e normaliza
    para 0-1 (escala do dataset). Sem chave ou em falha, retorna None e avisa uma
    vez no stderr (nao falha em silencio).
    """
    global _PR_WARNED
    key = (os.environ.get("OPENPAGERANK_API_KEY") or "").strip()
    if not key:
        return None
    domain = host[4:] if host.startswith("www.") else host
    try:
        resp = requests.post(
            "https://openpagerank.keywordseverywhere.com/v1/domains/bulk",
            headers={"Authorization": f"Bearer {key}"},
            json={"domains": [domain], "include_history": False},
        )
        data = resp.json()
        results = data.get("results") or []

        if not results:
            return None

        row = results[0]
        print("resultado: ", row)
        pr = row.get("open_page_rank")
        if not row.get("found") or pr is None:
            return None
        # Open PageRank retorna 0-10; o dataset usa 0-1 -> normaliza.
        return round(float(pr), 3)
    except Exception as exc:
        if not _PR_WARNED:
            _PR_WARNED = True
            print(
                f"[features] Open PageRank indisponivel ({exc}); "
                "page_rank sera omitido. Verifique OPENPAGERANK_API_KEY.",
                file=sys.stderr,
            )
        return None


# Extratores de rede por feature: so sao chamados quando a feature esta em
# FEATURE_COLUMNS, evitando consultas caras para features desativadas.
_NETWORK_EXTRACTORS = {
    "activate_days": _whois_activate_days,
    "certificate": _tls_certificate_days,
    "page_rank": _open_pagerank,
}


def extract_network_features(
    url: str, columns: Iterable[str] = FEATURE_COLUMNS, timeout: float = 4.0
) -> dict[str, Any]:
    """Features que exigem consultas externas (WHOIS/TLS/PageRank).

    So executa o lookup de uma feature se ela estiver em ``columns``. Cada lookup
    tem timeout curto e degrada para ``None`` em falha.
    """
    cols = set(columns)
    host = urlsplit(url).hostname or ""
    out: dict[str, Any] = {}
    for name, extractor in _NETWORK_EXTRACTORS.items():
        if name not in cols:
            continue
        out[name] = extractor(host, timeout) if host else None
    return out


def extract_features(
    url: str, columns: Iterable[str] = FEATURE_COLUMNS, timeout: float = 4.0
) -> dict[str, Any]:
    """Todas as features configuradas derivaveis no servidor: URL + rede.

    Guiado por ``columns`` (default: FEATURE_COLUMNS): so calcula (e so consulta a
    rede para) as features usadas no treino. As features de DOM (html_input,
    iframe, redirect) vem da extensao e sao mescladas por quem chama.
    """
    feats = extract_url_features(url, columns)
    feats.update(extract_network_features(url, columns, timeout))
    return feats
