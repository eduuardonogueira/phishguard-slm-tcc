"""Configuracao central do pipeline SLM de deteccao de phishing.

Todos os caminhos sao relativos a raiz do projeto (dois niveis acima deste
arquivo: ``src/phishguard_slm/config.py`` -> raiz). Hiperparametros tem
padroes sensatos e podem ser sobrescritos pela CLI.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]

# Carrega variaveis do .env da raiz (ex.: OPENPAGERANK_API_KEY) para o ambiente,
# antes de qualquer leitura de os.environ. Importar config cedo (todo o pacote
# faz) garante que a chave esteja disponivel.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ModuleNotFoundError:
    pass

# SLM le os dados brutos: dataset.csv, derivado do original do paper
# dataset_normalizado.csv (usado pelos modelos de ML). Ver experiments.py / featurize.py.
DATASET_CSV = ROOT / "datasets" / "paper" / "dataset.csv"
OUTPUTS = ROOT / "outputs"
ADAPTER_DIR = OUTPUTS / "adapter"
SPLITS_DIR = OUTPUTS / "splits"
REPORTS_DIR = OUTPUTS / "reports"

# ---------------------------------------------------------------------------
# Rotulos e colunas
# ---------------------------------------------------------------------------
URL_COLUMN = "url"
LABEL_COLUMN = "phishing"  # 1 = maliciosa, 0 = legitima

# Colunas de features (todas as demais colunas do dataset). Sao renderizadas
# como atributos textuais no prompt do SLM, permitindo que o modelo use o
# conjunto completo de sinais do dataset (nao apenas a string da URL).
FEATURE_COLUMNS: tuple[str, ...] = (
    "page_rank",
    "caract_hifen",
    "activate_days",
    "is_https",
    "html_input",
    "iframe",
    "dot_count",
    "https_text",
    "url_lenght",
    "suspect_char",
    "certificate",
    "ip_format",
    "redirect",
)

# Rotulos legiveis (PT-BR) usados para renderizar cada feature no prompt.
FEATURE_LABELS: dict[str, str] = {
    "url_lenght": "comprimento_url",
    "is_https": "usa_https",
    "ip_format": "dominio_e_ip",
    "dot_count": "qtd_pontos",
    "suspect_char": "caracteres_suspeitos",
    "html_input": "campos_input_html",
    "activate_days": "dias_dominio_ativo",
    "page_rank": "page_rank",
    "certificate": "certificado",
    "redirect": "redirecionamento",
    "https_text": "https_no_texto",
    "caract_hifen": "qtd_hifens",
    "iframe": "possui_iframe",
}

# Palavras-resposta usadas no paradigma generativo (PT-BR).
# "sim"  -> a URL E phishing (classe positiva = 1)
# "nao"  -> a URL NAO e phishing (classe negativa = 0)
POSITIVE_WORD = "sim"
NEGATIVE_WORD = "nao"


@dataclass
class Config:
    """Parametros do pipeline."""

    # Modelo base (HuggingFace Hub).
    model_id: str = "Qwen/Qwen2.5-0.5B-Instruct"

    # Reprodutibilidade.
    seed: int = 42

    # Splits estratificados (fracoes do total).
    test_size: float = 0.15
    val_size: float = 0.15  # fracao do total (nao do restante)

    # Proporcao realista de phishing no cenario de trafego real (~5-10%).
    realistic_phishing_rate: float = 0.07

    # LoRA / SFT.
    epochs: int = 1
    learning_rate: float = 2e-4
    batch_size: int = 8
    grad_accum: int = 2
    max_len: int = 384  # URL + 13 atributos no prompt (~p95=365 tokens) + resposta
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    lora_target_modules: tuple[str, ...] = (
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
    )

    # Limite opcional de exemplos (smoke tests / maquinas modestas).
    max_train_samples: int | None = None
    max_eval_samples: int | None = None

    # Few-shot: numero de exemplos no prompt para o modo zero/few-shot.
    num_fewshot: int = 0

    # Limiar de decisao P(phishing) -> classe. Ajustado na validacao pelo eval.
    threshold: float = 0.5

    # Cross-dataset opcional (mesmo schema do datasets/paper/dataset.csv, bruto).
    external_csv: Path | None = None

    # Caminhos (preenchidos a partir dos defaults acima).
    dataset_csv: Path = field(default=DATASET_CSV)
    adapter_dir: Path = field(default=ADAPTER_DIR)
    reports_dir: Path = field(default=REPORTS_DIR)

    def ensure_dirs(self) -> None:
        for d in (OUTPUTS, ADAPTER_DIR, SPLITS_DIR, REPORTS_DIR):
            d.mkdir(parents=True, exist_ok=True)


def resolve_device(prefer_cpu: bool = False) -> str:
    """Escolhe o device de execucao.

    ``prefer_cpu`` forca CPU (cenario de latencia on-device / extensao). Caso
    contrario usa MPS (Apple Silicon) quando disponivel, senao CUDA, senao CPU.
    """

    import torch

    if prefer_cpu:
        return "cpu"
    if torch.backends.mps.is_available():
        # Permite fallback de ops nao implementadas em MPS para CPU.
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def model_dtype(model_id: str, device: str):
    """dtype de carga do modelo no device.

    Gemma 3 transborda em float16 (ativacoes grandes): usa bfloat16 na GPU que
    suporta e float32 no resto. Os demais usam float16 fora da CPU.
    """
    import torch

    if device == "cpu":
        return torch.float32
    if "gemma" in model_id.lower():
        if device == "cuda" and torch.cuda.is_bf16_supported():
            return torch.bfloat16
        return torch.float32
    return torch.float16

