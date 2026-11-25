"""Construcao de prompts PT-BR e mapeamento de rotulos.

Mantem zero-shot e fine-tuned no MESMO formato de chat, para uma comparacao
justa. A resposta esperada e uma unica palavra: ``sim`` (phishing) ou ``nao``
(legitima). O ``scoring`` compara o log-prob das duas candidatas, entao a
tokenizacao exata da palavra nao importa.
"""

from __future__ import annotations

from typing import Any, Mapping

from .config import FEATURE_COLUMNS, FEATURE_LABELS, NEGATIVE_WORD, POSITIVE_WORD

SYSTEM_PROMPT = (
    "Voce e um detector de phishing especializado em URLs, inclusive marcas e "
    "servicos brasileiros (PIX, gov.br, bancos nacionais). Analise a URL e os "
    "atributos extraidos e responda apenas com 'sim' se for phishing/maliciosa "
    "ou 'nao' se for legitima. Responda somente uma palavra, sem explicacao."
)

USER_TEMPLATE = "A URL a seguir e phishing?\nURL: {url}"


def _missing(value: Any) -> bool:
    """None, NaN ou pd.NA: a feature nao foi obtida e sai do prompt."""
    if value is None:
        return True
    try:
        return bool(value != value) or str(value) == "<NA>"
    except (TypeError, ValueError):
        return False


def _format_value(value: Any) -> str:
    """Formata o valor de uma feature de forma compacta para o prompt."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        # Inteiros armazenados como float (1.0) -> "1"; decimais -> ate 4 sig.
        return str(int(value)) if value.is_integer() else f"{value:.4g}"
    return str(value)


def format_features(features: Mapping[str, Any] | None) -> str:
    """Renderiza as features como um bloco textual de atributos para o prompt.

    Retorna string vazia quando nenhuma feature esta disponivel (ex.: inferencia
    com apenas a URL crua vinda da extensao), fazendo o prompt degradar para o
    formato somente-URL.
    """
    if not features:
        return ""
    lines = []
    for col in FEATURE_COLUMNS:
        val = features.get(col)
        if _missing(val):
            continue
        label = FEATURE_LABELS.get(col, col)
        lines.append(f"- {label}: {_format_value(val)}")
    if not lines:
        return ""
    return "\nAtributos extraidos:\n" + "\n".join(lines)

# Poucos exemplos representativos para o modo few-shot (rotulos ja resolvidos).
FEWSHOT_EXAMPLES: list[tuple[str, int]] = [
    ("https://www.google.com/", 0),
    ("https://android.com", 0),
    ("http://bb-atualizacao-cadastro.com/pix/login", 1),
    ("https://caixa.gov.br.seguranca-cliente.win/acesso", 1),
    ("https://github.com/torvalds/linux", 0),
    ("http://192.168.10.5/itau/token/validar.php", 1),
]


def label_to_word(label: int) -> str:
    """1 -> 'sim', 0 -> 'nao'."""
    return POSITIVE_WORD if int(label) == 1 else NEGATIVE_WORD


def build_messages(
    url: str,
    features: Mapping[str, Any] | None = None,
    num_fewshot: int = 0,
) -> list[dict[str, str]]:
    """Monta a lista de mensagens de chat para uma URL e seus atributos.

    ``features`` e um mapeamento coluna->valor (as colunas de ``FEATURE_COLUMNS``).
    Quando ausente, o prompt usa apenas a URL. Com ``num_fewshot`` > 0, insere
    pares (user, assistant) de exemplo antes da pergunta final.
    """

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    for ex_url, ex_label in FEWSHOT_EXAMPLES[: max(0, num_fewshot)]:
        messages.append({"role": "user", "content": USER_TEMPLATE.format(url=ex_url)})
        messages.append({"role": "assistant", "content": label_to_word(ex_label)})

    user_content = USER_TEMPLATE.format(url=url) + format_features(features)
    messages.append({"role": "user", "content": user_content})
    return messages


def candidate_words() -> tuple[str, str]:
    """Retorna (palavra_positiva, palavra_negativa) = ('sim', 'nao')."""
    return POSITIVE_WORD, NEGATIVE_WORD
