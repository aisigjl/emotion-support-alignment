# GPT-4o Training Data Distillation

## 1. Target Scale

The recommended first formal version uses this data scale:

```text
Eval: 450 samples
SFT:  5000 chat samples
DPO:  1500 preference pairs
```

The purpose is to build a credible portfolio-grade post-training loop, not to exhaust the full SMILE corpus.

## 2. File-Level Split

Before distillation, create a file-level split manifest:

```bash
python scripts/prepare_data_split.py   --raw-dir data/raw/smile   --output-path data/processed/smile_split_manifest.json   --sft-ratio 0.70   --dpo-ratio 0.15   --eval-ratio 0.15   --seed 42
```

Current local split summary:

```text
total_files: 55165
sft: 38615
dpo: 8274
eval: 8276
```

The split is at raw-file level. A SMILE JSON file belongs to exactly one split, so the same source dialogue cannot enter both training and evaluation.

## 3. Eval Distillation

Build the 450-sample mixed eval set:

```bash
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY   python scripts/distill_public_eval_with_gpt4o.py   --manifest-path data/processed/smile_split_manifest.json   --split eval   --target-count 250   --max-files 400   --samples-per-file 2   --build-mixed   --public-count 250   --synthetic-count 150   --redteam-count 50   --continue-on-error   --retry-errors
```

This creates:

```text
data/eval/public_gpt4o_distilled_eval.jsonl
data/eval/base_eval_v2_mixed.jsonl
```

## 4. SFT Distillation

Build 5000 SFT chat samples:

```bash
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY   python scripts/distill_sft_with_gpt4o.py   --manifest-path data/processed/smile_split_manifest.json   --split sft   --target-count 5000   --max-files 6000   --samples-per-file 1   --output-path data/processed/sft_train.jsonl   --summary-path data/processed/sft_train_summary.json   --processed-log-path data/processed/sft_distilled_processed.jsonl   --continue-on-error   --retry-errors
```

Each row contains:

```text
messages: system + user + assistant
scenario
risk_level
user_input
assistant_response
source_metadata.raw_file
```

The assistant response is rewritten by GPT-4o and filtered by project safety heuristics.

## 5. DPO Distillation

Build 1500 DPO preference pairs:

```bash
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY   python scripts/distill_dpo_with_gpt4o.py   --manifest-path data/processed/smile_split_manifest.json   --split dpo   --target-count 1500   --max-files 2500   --pairs-per-file 1   --output-path data/processed/dpo_train.jsonl   --summary-path data/processed/dpo_train_summary.json   --processed-log-path data/processed/dpo_distilled_processed.jsonl   --continue-on-error   --retry-errors
```

Each row contains TRL-compatible conversational preference fields:

```text
prompt:   system + user
chosen:   assistant message list
rejected: assistant message list
```

`chosen` is a safe, higher-quality response. `rejected` is a plausible weaker response with a clear preference issue, but it is filtered to avoid concrete self-harm, violence, or medication dosage instructions.

## 6. Resume Behavior

All three distillation scripts write output incrementally and keep a processed-file log.

Resume after interruption:

```text
run the same command again
```

Retry previous API/network error files:

```text
add --retry-errors
```

Continue past new API/file errors:

```text
add --continue-on-error
```

Rebuild from scratch:

```text
add --overwrite
```

Do not use `--overwrite` during normal resume.

## 7. Recommended Execution Order

```text
1. python scripts/prepare_data_split.py ...
2. Eval smoke test: target-count 20-30
3. SFT smoke test: target-count 20-30
4. DPO smoke test: target-count 20-30
5. Build full Eval 450
6. Build full SFT 5000
7. Build full DPO 1500
8. Train SFT
9. Train DPO
10. Evaluate base / SFT / SFT+DPO on the same fixed eval set
```

## 8. Quality Checks

Before training, manually inspect at least:

```text
SFT: 50 rows
DPO: 50 pairs
Eval: 30 rows
```

Reject or regenerate data if you see:

- diagnosis presented as fact
- medication names, dosage, stopping, switching, or self-medication advice
- crisis expressions handled as ordinary chat
- assistant dependency language
- overlong, generic, or lecture-like responses
- near-duplicate user inputs

## 9. OpenAI API Notes

The scripts use the OpenAI Python SDK and Chat Completions with JSON-object output when the configured endpoint supports it. If your gateway rejects `response_format`, the helper retries without JSON mode and parses the JSON object from the returned text.

Relevant official OpenAI documentation:

- OpenAI Chat Completions API: https://platform.openai.com/docs/api-reference/chat/create
- OpenAI Python SDK: https://github.com/openai/openai-python
