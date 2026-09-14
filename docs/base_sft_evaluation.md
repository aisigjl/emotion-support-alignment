# Base and SFT Evaluation

Use the same fixed evaluation set for base and SFT:

```text
data/eval/base_eval_v2_mixed.jsonl
```

This file has 449 samples. Pass `--limit 0` to evaluate all rows. The default `NUM_SAMPLES` is 400, so do not rely on the default for final comparison.

## Smoke Tests Already Run

Base smoke generation:

```bash
CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/eval.py generate   --data-path data/eval/base_eval_v2_mixed.jsonl   --responses-path outputs/baseline/base_eval_v2_smoke_responses.jsonl   --model-path /home/WangChanghui/wch/model/Qwen3-4B-Instruct-2507   --model-name qwen3_4b_base   --limit 3   --batch-size 1   --max-new-tokens 256   --overwrite
```

SFT smoke generation:

```bash
CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/eval.py generate   --data-path data/eval/base_eval_v2_mixed.jsonl   --responses-path outputs/sft/sft_eval_v2_smoke_responses.jsonl   --model-path /home/WangChanghui/wch/model/Qwen3-4B-Instruct-2507   --adapter-path outputs/sft/qwen3_4b_sft_lora   --model-name qwen3_4b_sft_lora   --limit 3   --batch-size 1   --max-new-tokens 256   --overwrite
```

Both smoke runs produced non-empty responses with no local rule flags.

## Full Base Evaluation

Run generation, judge, and summary:

```bash
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/eval.py all   --data-path data/eval/base_eval_v2_mixed.jsonl   --responses-path outputs/baseline/base_eval_v2_responses.jsonl   --judge-path outputs/baseline/base_eval_v2_judge.jsonl   --summary-path outputs/baseline/base_eval_v2_summary.json   --report-path outputs/eval_reports/base_eval_v2_report.md   --model-path /home/WangChanghui/wch/model/Qwen3-4B-Instruct-2507   --model-name qwen3_4b_base   --limit 0   --batch-size 4   --max-new-tokens 512   --temperature 0
```

## Full SFT Evaluation

Run generation, judge, and summary with the SFT LoRA adapter:

```bash
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/eval.py all   --data-path data/eval/base_eval_v2_mixed.jsonl   --responses-path outputs/sft/sft_eval_v2_responses.jsonl   --judge-path outputs/sft/sft_eval_v2_judge.jsonl   --summary-path outputs/sft/sft_eval_v2_summary.json   --report-path outputs/eval_reports/sft_eval_v2_report.md   --model-path /home/WangChanghui/wch/model/Qwen3-4B-Instruct-2507   --adapter-path outputs/sft/qwen3_4b_sft_lora   --model-name qwen3_4b_sft_lora   --limit 0   --batch-size 4   --max-new-tokens 512   --temperature 0
```

## Resume Rules

The eval script resumes by `id`. If a command stops halfway, rerun the same command without `--overwrite`.

Use `--overwrite` only when intentionally rebuilding an output file from scratch.

## Recommended Order

1. Run full base evaluation.
2. Run full SFT evaluation.
3. Compare `outputs/baseline/base_eval_v2_summary.json` and `outputs/sft/sft_eval_v2_summary.json`.
4. Read the two Markdown reports under `outputs/eval_reports/`.
5. Only then start DPO training and SFT+DPO evaluation.

It is okay that base evaluation was not run before SFT training. The base model is unchanged, and the eval split is held out from SFT/DPO data. The important rule is that base and SFT are evaluated on the same fixed eval set with the same judge rubric.
