# SFT Training

This stage trains a LoRA/QLoRA adapter for the local base model:

```text
/home/WangChanghui/wch/model/Qwen3-4B-Instruct-2507
```

The default config is:

```text
configs/sft_lora_qwen3_4b.json
```

Run a smoke test first:

```bash
CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/train_sft.py \
  --config configs/sft_lora_qwen3_4b.json \
  --output-dir outputs/sft/smoke_qwen3_4b_sft_lora \
  --max-train-samples 16 \
  --max-eval-samples 4 \
  --eval-size 4 \
  --max-steps 2 \
  --overwrite-output-dir
```

Run the full SFT training:

```bash
CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/train_sft.py \
  --config configs/sft_lora_qwen3_4b.json
```

Resume from a checkpoint:

```bash
CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/train_sft.py \
  --config configs/sft_lora_qwen3_4b.json \
  --resume-from-checkpoint outputs/sft/qwen3_4b_sft_lora/checkpoint-100
```

The script trains only the assistant response tokens by default. The system and user prompt tokens are masked with `-100`.
