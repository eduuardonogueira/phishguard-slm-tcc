"""Fine-tuning LoRA (SFT) do SLM para classificacao de URL.

Cada exemplo e o prompt de chat (URL) com a resposta esperada (``sim``/``nao``)
como completion. A loss e mascarada para incidir apenas sobre os tokens da
resposta (o prompt entra como contexto).
"""

from __future__ import annotations

import pandas as pd
import torch
from datasets import Dataset

from pathlib import Path

from .config import FEATURE_COLUMNS, LABEL_COLUMN, URL_COLUMN, Config, model_dtype, resolve_device
from .data import build_splits
from .prompting import build_messages, label_to_word


def _build_hf_dataset(
    df: pd.DataFrame, tokenizer, cfg: Config, feature_columns=FEATURE_COLUMNS
) -> Dataset:
    """Tokeniza prompt+resposta com labels mascarados no trecho do prompt."""

    feature_cols = [c for c in feature_columns if c in df.columns]

    def encode(example: dict) -> dict:
        features = {c: example[c] for c in feature_cols}
        messages = build_messages(example[URL_COLUMN], features=features, num_fewshot=0)
        prompt_text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        answer = label_to_word(example[LABEL_COLUMN])
        prompt_ids = tokenizer.encode(prompt_text, add_special_tokens=False)
        answer_ids = tokenizer.encode(answer, add_special_tokens=False)
        answer_ids = answer_ids + [tokenizer.eos_token_id]

        # Trunca apenas o prompt (URLs/features muito longas), preservando SEMPRE
        # os tokens da resposta rotulada. Truncar o final cortaria o 'sim'/'nao'
        # e zeraria o sinal de treino do exemplo.
        max_prompt = max(1, cfg.max_len - len(answer_ids))
        prompt_ids = prompt_ids[:max_prompt]

        input_ids = prompt_ids + answer_ids
        labels = [-100] * len(prompt_ids) + answer_ids
        return {"input_ids": input_ids, "labels": labels}

    cols = df[[URL_COLUMN, LABEL_COLUMN, *feature_cols]].astype(object)
    cols = cols.where(cols.notna(), None).to_dict("records")
    ds = Dataset.from_list(cols)
    return ds.map(encode, remove_columns=ds.column_names)


class _Collator:
    """Padding dinamico de input_ids/labels/attention_mask."""

    def __init__(self, pad_id: int) -> None:
        self.pad_id = pad_id

    def __call__(self, features: list[dict]) -> dict[str, torch.Tensor]:
        max_len = max(len(f["input_ids"]) for f in features)
        input_ids, labels, attn = [], [], []
        for f in features:
            n = len(f["input_ids"])
            pad = max_len - n
            input_ids.append(f["input_ids"] + [self.pad_id] * pad)
            labels.append(f["labels"] + [-100] * pad)
            attn.append([1] * n + [0] * pad)
        return {
            "input_ids": torch.tensor(input_ids),
            "labels": torch.tensor(labels),
            "attention_mask": torch.tensor(attn),
        }


def train_lora(
    cfg: Config,
    train_df: pd.DataFrame | None = None,
    feature_columns=FEATURE_COLUMNS,
    out_dir: Path | None = None,
) -> dict:
    """Treina o LoRA e salva em ``out_dir`` (padrao: ``cfg.adapter_dir``).

    Sem ``train_df`` usa o split de treino do ``cfg.dataset_csv`` (modo antigo).
    Retorna um resumo (exemplos, segundos, loss final) para o manifesto do run.
    """
    import time

    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )

    cfg.ensure_dirs()
    device = resolve_device(prefer_cpu=False)

    tokenizer = AutoTokenizer.from_pretrained(cfg.model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    out_dir = Path(out_dir or cfg.adapter_dir)
    if train_df is None:
        train_df = build_splits(cfg).train
    if cfg.max_train_samples:
        train_df = train_df.sample(
            n=min(cfg.max_train_samples, len(train_df)), random_state=cfg.seed
        ).reset_index(drop=True)
    print(f"[train] exemplos de treino: {len(train_df)}  (device={device})")

    train_ds = _build_hf_dataset(train_df, tokenizer, cfg, feature_columns)

    dtype = model_dtype(cfg.model_id, device)
    extra = {"attn_implementation": "eager"} if "gemma" in cfg.model_id.lower() else {}
    model = AutoModelForCausalLM.from_pretrained(cfg.model_id, dtype=dtype, **extra)
    model.config.use_cache = False

    lora = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        target_modules=list(cfg.lora_target_modules),
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    use_fp16 = device == "cuda" and dtype == torch.float16
    use_bf16 = device == "cuda" and dtype == torch.bfloat16
    args = TrainingArguments(
        output_dir=str(out_dir / "_trainer"),
        num_train_epochs=cfg.epochs,
        per_device_train_batch_size=cfg.batch_size,
        gradient_accumulation_steps=cfg.grad_accum,
        learning_rate=cfg.learning_rate,
        logging_steps=25,
        save_strategy="no",
        report_to=[],
        fp16=use_fp16,
        bf16=use_bf16,
        seed=cfg.seed,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        data_collator=_Collator(tokenizer.pad_token_id),
    )
    t0 = time.time()
    out = trainer.train()
    secs = time.time() - t0

    model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))
    import shutil

    shutil.rmtree(out_dir / "_trainer", ignore_errors=True)
    print(f"[train] adapter salvo em: {out_dir}")
    return {
        "n_train": len(train_df),
        "device": device,
        "dtype": str(dtype).replace("torch.", ""),
        "train_seconds": round(secs, 1),
        "train_loss": round(float(out.training_loss), 5),
    }
