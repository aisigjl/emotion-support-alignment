from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "sft_lora_qwen3_4b.json"


def project_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Bad JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Bad row at {path}:{line_no}: expected object")
            rows.append(row)
    return rows


def apply_chat_template(tokenizer: Any, messages: list[dict[str, str]], *, add_generation_prompt: bool) -> str:
    try:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=add_generation_prompt,
            enable_thinking=False,
        )
    except TypeError:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=add_generation_prompt,
        )


def build_feature(
    tokenizer: Any,
    row: dict[str, Any],
    *,
    max_length: int,
    assistant_only_loss: bool,
) -> dict[str, Any]:
    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) != 3:
        raise ValueError(f"{row.get('id')} has bad messages")
    roles = [message.get("role") for message in messages if isinstance(message, dict)]
    if roles != ["system", "user", "assistant"]:
        raise ValueError(f"{row.get('id')} has bad roles: {roles}")

    full_text = apply_chat_template(tokenizer, messages, add_generation_prompt=False)
    full = tokenizer(full_text, add_special_tokens=False, truncation=True, max_length=max_length)
    input_ids = list(full["input_ids"])
    labels = list(input_ids)

    if assistant_only_loss:
        prompt_text = apply_chat_template(tokenizer, messages[:-1], add_generation_prompt=True)
        prompt = tokenizer(prompt_text, add_special_tokens=False, truncation=True, max_length=max_length)
        prompt_ids = list(prompt["input_ids"])
        prompt_len = min(len(prompt_ids), len(input_ids))
        if input_ids[:prompt_len] != prompt_ids[:prompt_len]:
            raise ValueError(f"{row.get('id')} prompt tokens are not a prefix of full tokens")
        labels[:prompt_len] = [-100] * prompt_len
        if all(label == -100 for label in labels):
            raise ValueError(f"{row.get('id')} has no assistant tokens after truncation")

    return {
        "id": row.get("id"),
        "input_ids": input_ids,
        "attention_mask": [1] * len(input_ids),
        "labels": labels,
    }


def prepare_dataset(
    tokenizer: Any,
    rows: list[dict[str, Any]],
    *,
    max_length: int,
    assistant_only_loss: bool,
) -> Any:
    from datasets import Dataset

    features = [
        build_feature(
            tokenizer,
            row,
            max_length=max_length,
            assistant_only_loss=assistant_only_loss,
        )
        for row in rows
    ]
    return Dataset.from_list(features)


@dataclass
class CausalLMDataCollator:
    tokenizer: Any
    pad_to_multiple_of: int | None = 8

    def __call__(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        import torch

        max_len = max(len(feature["input_ids"]) for feature in features)
        if self.pad_to_multiple_of:
            remainder = max_len % self.pad_to_multiple_of
            if remainder:
                max_len += self.pad_to_multiple_of - remainder

        pad_id = self.tokenizer.pad_token_id
        batch: dict[str, list[list[int]]] = {"input_ids": [], "attention_mask": [], "labels": []}
        for feature in features:
            length = len(feature["input_ids"])
            pad_len = max_len - length
            batch["input_ids"].append(feature["input_ids"] + [pad_id] * pad_len)
            batch["attention_mask"].append(feature["attention_mask"] + [0] * pad_len)
            batch["labels"].append(feature["labels"] + [-100] * pad_len)

        return {key: torch.tensor(value, dtype=torch.long) for key, value in batch.items()}


def split_rows(
    rows: list[dict[str, Any]],
    *,
    eval_size: int,
    seed: int,
    max_train_samples: int | None,
    max_eval_samples: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    eval_size = max(0, min(eval_size, len(shuffled) - 1))
    eval_rows = shuffled[:eval_size]
    train_rows = shuffled[eval_size:]
    if max_train_samples and max_train_samples > 0:
        train_rows = train_rows[:max_train_samples]
    if max_eval_samples and max_eval_samples > 0:
        eval_rows = eval_rows[:max_eval_samples]
    return train_rows, eval_rows


def load_model_and_tokenizer(cfg: dict[str, Any]) -> tuple[Any, Any]:
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    model_path = str(project_path(cfg["model_path"]))
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    tokenizer.padding_side = "right"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    compute_dtype = torch.bfloat16 if cfg.get("bf16", True) else torch.float16
    quantization_config = None
    if cfg.get("use_qlora", True) and cfg.get("load_in_4bit", True):
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=cfg.get("bnb_4bit_quant_type", "nf4"),
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=bool(cfg.get("bnb_4bit_use_double_quant", True)),
        )

    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        trust_remote_code=True,
        torch_dtype=compute_dtype,
        quantization_config=quantization_config,
        device_map="auto" if torch.cuda.is_available() else None,
        low_cpu_mem_usage=True,
    )
    model.config.use_cache = False

    if cfg.get("use_qlora", True):
        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=bool(cfg.get("gradient_checkpointing", True)),
        )

    lora_config = LoraConfig(
        r=int(cfg.get("lora_r", 16)),
        lora_alpha=int(cfg.get("lora_alpha", 32)),
        lora_dropout=float(cfg.get("lora_dropout", 0.05)),
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=list(cfg.get("lora_target_modules", [])),
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model, tokenizer


def train(cfg: dict[str, Any]) -> None:
    import torch
    from transformers import Trainer, TrainingArguments, set_seed

    if cfg.get("tf32", True) and torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = True

    seed = int(cfg.get("seed", 42))
    set_seed(seed)

    train_path = project_path(cfg["train_path"])
    output_dir = project_path(cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(train_path)
    train_rows, eval_rows = split_rows(
        rows,
        eval_size=int(cfg.get("eval_size", 0)),
        seed=seed,
        max_train_samples=cfg.get("max_train_samples"),
        max_eval_samples=cfg.get("max_eval_samples"),
    )

    model, tokenizer = load_model_and_tokenizer(cfg)
    train_dataset = prepare_dataset(
        tokenizer,
        train_rows,
        max_length=int(cfg.get("max_length", 1024)),
        assistant_only_loss=bool(cfg.get("assistant_only_loss", True)),
    )
    eval_dataset = None
    if eval_rows:
        eval_dataset = prepare_dataset(
            tokenizer,
            eval_rows,
            max_length=int(cfg.get("max_length", 1024)),
            assistant_only_loss=bool(cfg.get("assistant_only_loss", True)),
        )

    eval_steps = int(cfg.get("eval_steps", 0))
    save_steps = int(cfg.get("save_steps", 100))
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        overwrite_output_dir=bool(cfg.get("overwrite_output_dir", False)),
        do_train=True,
        do_eval=eval_dataset is not None,
        eval_strategy="steps" if eval_dataset is not None and eval_steps > 0 else "no",
        eval_steps=eval_steps if eval_dataset is not None and eval_steps > 0 else None,
        per_device_train_batch_size=int(cfg.get("per_device_train_batch_size", 2)),
        per_device_eval_batch_size=int(cfg.get("per_device_eval_batch_size", 2)),
        gradient_accumulation_steps=int(cfg.get("gradient_accumulation_steps", 8)),
        learning_rate=float(cfg.get("learning_rate", 2e-4)),
        weight_decay=float(cfg.get("weight_decay", 0.0)),
        max_grad_norm=float(cfg.get("max_grad_norm", 1.0)),
        num_train_epochs=float(cfg.get("num_train_epochs", 2.0)),
        max_steps=int(cfg.get("max_steps", -1)),
        warmup_ratio=float(cfg.get("warmup_ratio", 0.03)),
        logging_steps=int(cfg.get("logging_steps", 10)),
        save_steps=save_steps,
        save_strategy="steps",
        save_total_limit=int(cfg.get("save_total_limit", 3)),
        bf16=bool(cfg.get("bf16", True)),
        tf32=bool(cfg.get("tf32", True)),
        gradient_checkpointing=bool(cfg.get("gradient_checkpointing", True)),
        optim=str(cfg.get("optim", "paged_adamw_8bit")),
        lr_scheduler_type=str(cfg.get("lr_scheduler_type", "cosine")),
        report_to=str(cfg.get("report_to", "none")),
        remove_unused_columns=False,
        dataloader_num_workers=int(cfg.get("dataloader_num_workers", 0)),
        save_safetensors=True,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=CausalLMDataCollator(tokenizer),
    )
    trainer.train(resume_from_checkpoint=cfg.get("resume_from_checkpoint"))
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    write_json(
        output_dir / "training_metadata.json",
        {
            "model_path": str(project_path(cfg["model_path"])),
            "train_path": str(train_path),
            "train_rows": len(train_rows),
            "eval_rows": len(eval_rows),
            "output_dir": str(output_dir),
            "assistant_only_loss": bool(cfg.get("assistant_only_loss", True)),
            "use_qlora": bool(cfg.get("use_qlora", True)),
            "max_length": int(cfg.get("max_length", 1024)),
            "max_steps": int(cfg.get("max_steps", -1)),
            "num_train_epochs": float(cfg.get("num_train_epochs", 2.0)),
        },
    )


def merge_config(config_path: Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = read_json(config_path)
    overrides = {
        "model_path": args.model_path,
        "train_path": args.train_path,
        "output_dir": args.output_dir,
        "max_steps": args.max_steps,
        "num_train_epochs": args.num_train_epochs,
        "max_train_samples": args.max_train_samples,
        "max_eval_samples": args.max_eval_samples,
        "eval_size": args.eval_size,
        "resume_from_checkpoint": args.resume_from_checkpoint,
        "overwrite_output_dir": args.overwrite_output_dir,
    }
    for key, value in overrides.items():
        if value is not None:
            cfg[key] = value
    return cfg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train Qwen SFT LoRA/QLoRA adapter on distilled emotion-support data.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--model-path")
    parser.add_argument("--train-path")
    parser.add_argument("--output-dir")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--num-train-epochs", type=float)
    parser.add_argument("--max-train-samples", type=int)
    parser.add_argument("--max-eval-samples", type=int)
    parser.add_argument("--eval-size", type=int)
    parser.add_argument("--resume-from-checkpoint")
    parser.add_argument("--overwrite-output-dir", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    cfg = merge_config(project_path(args.config), args)
    train(cfg)


if __name__ == "__main__":
    main()
