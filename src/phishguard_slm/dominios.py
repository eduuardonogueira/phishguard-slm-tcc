"""Domínio registrado (eTLD+1) de uma URL, pela Public Suffix List embutida no tldextract.

A lista vem do próprio pacote (sem consulta à rede), de modo que o resultado depende só da
versão do tldextract fixada no ``uv.lock``. A seção privada da lista é incluída: subdomínios
de hospedagem compartilhada, como ``sites.google.com``, contam como domínios distintos.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from .config import ROOT

_extractors: dict[bool, object] = {}


def _extract(host: str, private: bool):
    import tldextract

    if private not in _extractors:
        _extractors[private] = tldextract.TLDExtract(
            cache_dir=str(ROOT / ".cache" / "tldextract"),
            suffix_list_urls=(),  # PSL embutida no pacote: sem rede, reprodutível
            include_psl_private_domains=private,
        )
    return _extractors[private](host)


def domain_info(url: str) -> dict:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        host = ""
    icann = _extract(host, private=False)
    priv = _extract(host, private=True)
    return {
        "host": host or None,
        "suffix": icann.suffix or None,
        "reg_domain": icann.top_domain_under_public_suffix or host or None,
        "reg_domain_private": priv.top_domain_under_public_suffix or host or None,
    }
