"""Carga do modelo e classificacao de URLs por log-prob de candidatas.

Para cada URL montamos o prompt de chat e comparamos o log-prob total das
respostas candidatas ``sim`` (phishing) e ``nao`` (legitima). A probabilidade
de phishing e o softmax sobre esses dois log-probs. Isso funciona para
qualquer tokenizacao das palavras-rotulo e fornece uma probabilidade continua
(com limiar ajustavel).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import torch

from .config import FEATURE_COLUMNS, Config, model_dtype, resolve_device
from .prompting import build_messages, candidate_words


@dataclass
class Prediction:
    url: str
    prob_phishing: float
    label: int
    latency_ms: float


class PhishClassifier:
    """Envolve tokenizer + modelo (base opcionalmente com adapter LoRA)."""

    def __init__(
        self,
        cfg: Config,
        adapter_dir: Path | None = None,
        prefer_cpu: bool = False,
        feature_columns: tuple[str, ...] | list[str] = FEATURE_COLUMNS,
    ) -> None:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.cfg = cfg
        self.feature_columns = tuple(feature_columns)
        self.device = resolve_device(prefer_cpu=prefer_cpu)

        self.tokenizer = AutoTokenizer.from_pretrained(cfg.model_id)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        dtype = model_dtype(cfg.model_id, self.device)
        model = AutoModelForCausalLM.from_pretrained(cfg.model_id, dtype=dtype)

        if adapter_dir is not None and Path(adapter_dir).exists():
            from peft import PeftModel

            model = PeftModel.from_pretrained(model, str(adapter_dir))
            model = model.merge_and_unload()  # funde LoRA -> inferencia mais rapida

        self.model = model.to(self.device).eval()

        # Pre-tokeniza as palavras-rotulo (com espaco inicial, como saida do assistant).
        pos_word, neg_word = candidate_words()
        self._cand_ids = {
            1: self.tokenizer.encode(pos_word, add_special_tokens=False),
            0: self.tokenizer.encode(neg_word, add_special_tokens=False),
        }

    # ------------------------------------------------------------------
    def _prompt_ids(self, url: str, features: Mapping[str, Any] | None = None) -> list[int]:
        messages = build_messages(url, features=features, num_fewshot=self.cfg.num_fewshot)
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        return self.tokenizer.encode(text, add_special_tokens=False)

    @torch.no_grad()
    def _candidate_logprob(self, prompt_ids: list[int], cand_ids: list[int]) -> float:
        """Log-prob total dos ``cand_ids`` dado o prompt (teacher forcing)."""
        input_ids = torch.tensor([prompt_ids + cand_ids], device=self.device)
        logits = self.model(input_ids).logits  # (1, T, V)
        # Posicoes que predizem cada token candidato: comecam no ultimo token do prompt.
        start = len(prompt_ids) - 1
        total = 0.0
        for i, tok in enumerate(cand_ids):
            step_logits = logits[0, start + i].float()
            logprobs = torch.log_softmax(step_logits, dim=-1)
            total += float(logprobs[tok])
        return total

    @torch.no_grad()
    def predict(self, url: str, features: Mapping[str, Any] | None = None) -> Prediction:
        t0 = time.perf_counter()
        prompt_ids = self._prompt_ids(url, features)
        pos, neg = self._cand_ids[1], self._cand_ids[0]
        if len(pos) == 1 and len(neg) == 1:
            # Um so passe: os dois candidatos saem da mesma posicao (mesmo valor
            # de antes, metade do custo).
            logits = self.model(torch.tensor([prompt_ids], device=self.device)).logits
            logprobs = torch.log_softmax(logits[0, -1].float(), dim=-1)
            lp_pos, lp_neg = float(logprobs[pos[0]]), float(logprobs[neg[0]])
        else:
            lp_pos = self._candidate_logprob(prompt_ids, pos)
            lp_neg = self._candidate_logprob(prompt_ids, neg)
        # softmax de dois escalares -> P(phishing)
        m = max(lp_pos, lp_neg)
        p_pos = torch.exp(torch.tensor(lp_pos - m))
        p_neg = torch.exp(torch.tensor(lp_neg - m))
        prob = float(p_pos / (p_pos + p_neg))
        latency = (time.perf_counter() - t0) * 1000.0
        label = int(prob >= self.cfg.threshold)
        return Prediction(url=url, prob_phishing=prob, label=label, latency_ms=latency)

    def predict_batch(self, urls: list[str]) -> list[Prediction]:
        return [self.predict(u) for u in urls]

    def predict_row(self, row: Mapping[str, Any]) -> Prediction:
        """Prediz a partir de uma linha do dataset (URL + features)."""
        from .config import URL_COLUMN

        features = {c: row[c] for c in self.feature_columns if c in row}
        return self.predict(row[URL_COLUMN], features=features)


def load_classifier(
    cfg: Config, use_adapter: bool = True, prefer_cpu: bool = False
) -> PhishClassifier:
    """Fabrica: carrega com ou sem o adapter LoRA fine-tunado."""
    adapter = cfg.adapter_dir if use_adapter else None
    return PhishClassifier(cfg, adapter_dir=adapter, prefer_cpu=prefer_cpu)
