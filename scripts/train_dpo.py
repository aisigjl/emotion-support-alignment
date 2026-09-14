from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.train_sft import apply_chat_template, project_path, read_json, read_jsonl, split_rows, write_json


DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "dpo_lora_qwen3_4b.json"


def require_one_message(row: dict[str, Any], key: str, role: str) -> dict[str, str]:
    messages = row.get(key)
    if not isinstance(messages, list) or len(messages) != 1:
        raise ValueError(f"{row.get('id')} has bad {key}: expected one message")
    message = messages[0]
    if not isinstance(message, dict) or message.get("role") != role:
        raise ValueError(f"{row.get('id')} has bad {key} role: {message}")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"{row.get('id')} has empty {key} content")
    return {"role": role, "content": content}


def format_pair(tokenizer: Any, row: dict[str, Any]) -> dict[str, str]:
    prompt_messages = row.get("prompt")
    if not isinstance(prompt_messages, list) or len(prompt_messages) < 2:
        raise ValueError(f"{row.get('id')} has bad prompt")
    roles = [message.get("role") for message in prompt_messages if isinstance(message, dict)]
    if roles[0] != "system" or roles[-1] != "user":
        raise ValueError(f"{row.get('id')} has bad prompt roles: {roles}")

    chosen = require_one_message(row, "chosen", "assistant")
    rejected = require_one_message(row, "rejected", "assistant")

    prompt_text = apply_chat_template(tokenizer, prompt_messages, add_generation_prompt=True)
    chosen_full = apply_chat_template(tokenizer, [*prompt_messages, chosen], add_generation_prompt=False)
    rejected_full = apply_chat_template(tokenizer, [*prompt_messages, rejected], add_generation_prompt=False)

    if not chosen_full.startswith(prompt_text):
        raise ValueError(f"{row.get('id')} chosen text is not prefixed by prompt text")
    if not rejected_full.startswith(prompt_text):
        raise ValueError(f"{row.get('id')} rejected text is not prefixed by prompt text")

    return {
        "prompt": prompt_text,
        "chosen": chosen_full[len(prompt_text) :].rstrip(),
        "rejected": rejected_full[len(prompt_text) :].rstrip(),
    }


def prepare_dataset(tokenizer: Any, rows: list[dict[str, Any]]) -> Any:
    from datasets import Dataset

    return Dataset.from_list([format_pair(tokenizer, row) for row in rows])


def build_quantization_config(cfg: dict[str, Any]) -> Any | None:
    import torch
    from transformers import BitsAndBytesConfig

    if not (cfg.get("use_qlora", True) and cfg.get("load_in_4bit", True)):
        return None

    compute_dtype = torch.bfloat16 if cfg.get("bf16", True) else torch.float16
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=cfg.get("bnb_4bit_quant_type", "nf4"),
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=bool(cfg.get("bnb_4bit_use_double_quant", True)),
    )


def load_base_model(cfg: dict[str, Any]) -> Any:
    import torch
    from transformers import AutoModelForCausalLM

    model_path = str(project_path(cfg["model_path"]))
    compute_dtype = torch.bfloat16 if cfg.get("bf16", True) else torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        trust_remote_code=True,
        torch_dtype=compute_dtype,
        quantization_config=build_quantization_config(cfg),
        device_map="auto" if torch.cuda.is_available() else None,
        low_cpu_mem_usage=True,
    )
    model.config.use_cache = False
    return model


def load_model_and_tokenizer(cfg: dict[str, Any]) -> tuple[Any, Any, Any]:
    import torch
    from peft import PeftModel, prepare_model_for_kbit_training
    from transformers import AutoTokenizer

    model_path = str(project_path(cfg["model_path"]))
    sft_adapter_path = str(project_path(cfg["sft_adapter_path"]))

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    tokenizer.padding_side = "right"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    policy_base = load_base_model(cfg)
    if cfg.get("use_qlora", True):
        policy_base = prepare_model_for_kbit_training(
            policy_base,
            use_gradient_checkpointing=bool(cfg.get("gradient_checkpointing", True)),
        )
    policy_model = PeftModel.from_pretrained(policy_base, sft_adapter_path, is_trainable=True)
    policy_model.config.use_cache = False
    policy_model.print_trainable_parameters()

    ref_base = load_base_model(cfg)
    ref_model = PeftModel.from_pretrained(ref_base, sft_adapter_path, is_trainable=False)
    ref_model.config.use_cache = False
    ref_model.eval()
    for parameter in ref_model.parameters():
        parameter.requires_grad_(False)

    if cfg.get("tf32", True) and torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = True

    return policy_model, ref_model, tokenizer


def train(cfg: dict[str, Any]) -> None:
    from transformers import set_seed
    from trl import DPOConfig, DPOTrainer

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

    policy_model, ref_model, tokenizer = load_model_and_tokenizer(cfg)
    train_dataset = prepare_dataset(tokenizer, train_rows)
    eval_dataset = prepare_dataset(tokenizer, eval_rows) if eval_rows else None

    eval_steps = int(cfg.get("eval_steps", 0))
    save_steps = int(cfg.get("save_steps", 100))
    training_args = DPOConfig(
        output_dir=str(output_dir),
        overwrite_output_dir=bool(cfg.get("overwrite_output_dir", False)),
        do_train=True,
        do_eval=eval_dataset is not None,
        eval_strategy="steps" if eval_dataset is not None and eval_steps > 0 else "no",
        eval_steps=eval_steps if eval_dataset is not None and eval_steps > 0 else None,
        per_device_train_batch_size=int(cfg.get("per_device_train_batch_size", 1)),
        per_device_eval_batch_size=int(cfg.get("per_device_eval_batch_size", 1)),
        gradient_accumulation_steps=int(cfg.get("gradient_accumulation_steps", 8)),
        learning_rate=float(cfg.get("learning_rate", 5e-6)),
        weight_decay=float(cfg.get("weight_decay", 0.0)),
        max_grad_norm=float(cfg.get("max_grad_norm", 1.0)),
        num_train_epochs=float(cfg.get("num_train_epochs", 1.0)),
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
        beta=float(cfg.get("beta", 0.1)),
        max_length=int(cfg.get("max_length", 1024)),
    )

    trainer = DPOTrainer(
        model=policy_model,
        ref_model=ref_model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
    )
    trainer.train(resume_from_checkpoint=cfg.get("resume_from_checkpoint"))
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    write_json(
        output_dir / "training_metadata.json",
        {
            "model_path": str(project_path(cfg["model_path"])),
            "sft_adapter_path": str(project_path(cfg["sft_adapter_path"])),
            "train_path": str(train_path),
            "train_rows": len(train_rows),
            "eval_rows": len(eval_rows),
            "output_dir": str(output_dir),
            "use_qlora": bool(cfg.get("use_qlora", True)),
            "max_length": int(cfg.get("max_length", 1024)),
            "beta": float(cfg.get("beta", 0.1)),
            "max_steps": int(cfg.get("max_steps", -1)),
            "num_train_epochs": float(cfg.get("num_train_epochs", 1.0)),
        },
    )


def merge_config(config_path: Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = read_json(config_path)
    overrides = {
        "model_path": args.model_path,
        "sft_adapter_path": args.sft_adapter_path,
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
    parser = argparse.ArgumentParser(description="Train Qwen DPO LoRA adapter from an SFT adapter.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--model-path")
    parser.add_argument("--sft-adapter-path")
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
