"""Figura da arquitetura da ferramenta (Seção 3.7 do TCC).

Desenha os componentes (extensão, servidor local, serviços externos) e o fluxo de
comunicação numerado entre eles. Não lê dados nem carrega modelos: o conteúdo
reflete o código em ``url-collector-extension/`` e ``src/phishguard_slm/server.py``.

Uso:  uv run --with matplotlib python scripts/tcc_arquitetura.py
Saída: outputs/figuras/arquitetura.png e outputs/figuras/arquitetura.pdf
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "outputs" / "figuras"

# Paleta sóbria, legível em impressão P&B.
FUNDO_GRUPO = "#F3F4F6"
BORDA_GRUPO = "#6B7280"
FUNDO_CAIXA = "#FFFFFF"
BORDA_CAIXA = "#374151"
DESTAQUE = "#DBEAFE"  # componentes alterados em relação ao trabalho-base
SETA = "#111827"
TEXTO = "#111827"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})


def grupo(ax, x, y, w, h, titulo):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2",
                                fc=FUNDO_GRUPO, ec=BORDA_GRUPO, lw=1.2, ls="--"))
    ax.text(x + w / 2, y + h - 1.6, titulo, ha="center", va="top", fontsize=10.5,
            fontweight="bold", color=TEXTO)


def caixa(ax, x, y, w, h, titulo, corpo="", destaque=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.8",
                                fc=DESTAQUE if destaque else FUNDO_CAIXA, ec=BORDA_CAIXA, lw=1.0))
    if corpo:
        ax.text(x + w / 2, y + h - 1.1, titulo, ha="center", va="top", fontsize=9,
                fontweight="bold", color=TEXTO)
        ax.text(x + w / 2, y + h - 3.6, corpo, ha="center", va="top", fontsize=7.8,
                color=TEXTO, linespacing=1.35)
    else:
        ax.text(x + w / 2, y + h / 2, titulo, ha="center", va="center", fontsize=9,
                fontweight="bold", color=TEXTO)


def seta(ax, p0, p1, n=None, rad=0.0, rotulo=None, off=(0, 0), estilo="-|>", ls="-"):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=estilo, mutation_scale=11, lw=1.1,
                                 color=SETA, ls=ls, connectionstyle=f"arc3,rad={rad}",
                                 shrinkA=2, shrinkB=2))
    mx, my = (p0[0] + p1[0]) / 2 + off[0], (p0[1] + p1[1]) / 2 + off[1]
    if n is not None:
        ax.add_patch(plt.Circle((mx, my), 1.25, fc=SETA, ec=SETA, zorder=5))
        ax.text(mx, my, str(n), ha="center", va="center", fontsize=8, color="white",
                fontweight="bold", zorder=6)
    if rotulo:
        ax.text(mx, my - 2.0, rotulo, ha="center", va="top", fontsize=7.5, color=TEXTO,
                style="italic", zorder=6)


def main() -> None:
    fig, ax = plt.subplots(figsize=(11.5, 6.6))
    ax.set_xlim(0, 113)
    ax.set_ylim(0, 66)
    ax.axis("off")

    # ---------------- Navegador ----------------
    grupo(ax, 1, 3, 46, 61, "Navegador Chrome")
    caixa(ax, 4, 47, 40, 7.5, "Página visitada (aba)",
          "DOM já renderizado; content.js exibe o aviso por 5 s", destaque=True)
    ax.add_patch(FancyBboxPatch((3, 5), 42, 35, boxstyle="round,pad=0,rounding_size=1",
                                fc="#E5E7EB", ec=BORDA_GRUPO, lw=1.0))
    ax.text(24, 7.6, "Extensão (Manifest V3)", ha="center", va="center",
            fontsize=9.5, fontweight="bold", color=TEXTO)
    caixa(ax, 5, 23, 12, 13, "Extrator DOM",
          "dom-features.js\nhtml_input,\niframe e\nredirect", destaque=True)
    caixa(ax, 19, 23, 24, 13, "Service worker",
          "background.js\nevento onCompleted\nfiltro de repetição (3 s)\nresposta à aba de origem",
          destaque=True)
    caixa(ax, 5, 10.5, 38, 10, "Popup",
          "liga/desliga a verificação automática\nverificação manual pelo mesmo endpoint",
          destaque=True)

    # ---------------- Servidor local ----------------
    grupo(ax, 52, 3, 34, 61, "Servidor local\n(Flask, 127.0.0.1:5000)")
    caixa(ax, 55, 49, 28, 7, "POST /receive_url", "recebe {url, features}")
    caixa(ax, 55, 36, 28, 10, "Extração de atributos",
          "léxicos: calculados da URL\nrede: idade, certificado, PageRank\nvalor ausente é omitido",
          destaque=True)
    caixa(ax, 55, 26.5, 28, 6.5, "Montagem do prompt",
          "URL + atributos em unidades originais", destaque=True)
    caixa(ax, 55, 14, 28, 9.5, "SLM: Qwen2.5-0.5B + LoRA",
          "execução em CPU\nP(phishing) = softmax(\"sim\", \"nao\")\nlimiar 0,5", destaque=True)
    caixa(ax, 55, 5, 28, 6.5, "Monitoramento",
          "GET /stats, /metrics, /dashboard, /health", destaque=True)

    # ---------------- Serviços externos ----------------
    grupo(ax, 90, 26, 22, 38, "Serviços externos")
    caixa(ax, 92, 50, 18, 6.5, "WHOIS", "idade do domínio")
    caixa(ax, 92, 40.5, 18, 6.5, "Site (porta 443)", "certificado TLS")
    caixa(ax, 92, 31, 18, 6.5, "Open PageRank", "API com chave")

    # ---------------- Fluxo ----------------
    seta(ax, (31, 47), (31, 36), n=1, off=(0, 2.0))                     # 1
    seta(ax, (11, 36), (11, 47), n=2, off=(0, 2.0), estilo="<|-|>", ls="--")  # 2
    seta(ax, (43, 33), (55, 52.5), n=3, rad=-0.25, off=(-1.0, 1.5))       # 3
    seta(ax, (69, 49), (69, 46))
    seta(ax, (69, 36), (69, 33))
    seta(ax, (69, 26.5), (69, 23.5), n=5, off=(3, 0))                     # 5
    seta(ax, (83, 43), (92, 53), n=4, off=(0, 0.3), estilo="<|-|>")        # 4
    seta(ax, (83, 41.5), (92, 43.5), estilo="<|-|>")
    seta(ax, (83, 40), (92, 34), estilo="<|-|>")
    seta(ax, (55, 18.5), (43, 26), n=6, rad=-0.2, off=(0, -1.0))           # 6
    seta(ax, (39, 36), (39, 47), n=7, off=(0, 2.0))                       # 7

    # ---------------- Legenda ----------------
    leg = [
        "1  Página termina de carregar",
        "2  Extração dos atributos do DOM na aba",
        "3  POST /receive_url com URL e atributos",
        "4  Consultas de rede (WHOIS, TLS, PageRank)",
        "5  Prompt → SLM → probabilidade",
        "6  Resposta JSON {message, type}",
        "7  Aviso exibido na página",
    ]
    ax.text(90, 23, "Fluxo de comunicação", fontsize=8.5, fontweight="bold", va="top",
            color=TEXTO)
    for i, s in enumerate(leg):
        ax.text(90, 20.3 - i * 2.15, s, fontsize=7.2, va="top", color=TEXTO)
    ax.add_patch(FancyBboxPatch((90, 3.2), 2.2, 1.4, boxstyle="square,pad=0", fc=DESTAQUE,
                                ec=BORDA_CAIXA, lw=0.8))
    ax.text(93, 3.9, "alterado em relação\nao trabalho-base", fontsize=7, va="center",
            color=TEXTO)

    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "arquitetura.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / "arquitetura.pdf", bbox_inches="tight", facecolor="white")
    print(OUT / "arquitetura.png")


if __name__ == "__main__":
    main()
