# Baseline Generation and API Evaluation Pipeline

## 1. Purpose

`scripts/eval.py` provides the first evaluation pipeline for this project:

```text
base_eval.jsonl -> local Qwen generation -> GPT-4o/API judge -> summary/report
```

It supports resume by default. If an output JSONL already contains an `id`, that sample will be skipped unless `--overwrite` is used.

## 2. Files

Input:

```text
data/eval/base_eval.jsonl
```

Generated base-model responses:

```text
outputs/baseline/Qwen3_4b_instruct_2507_base_responses.jsonl
```

API judge results:

```text
outputs/baseline/Qwen3_4b_instruct_2507_base_judge.jsonl
```

Summary JSON:

```text
outputs/baseline/Qwen3_4b_instruct_2507_base_eval_summary.json
```

Markdown report:

```text
outputs/eval_reports/Qwen3_4b_instruct_2507_base_baseline_eval_report.md
```

## 3. Run Local Base Model Generation

From the project root:

```bash
python scripts/eval.py generate
```

For a small smoke test:

```bash
python scripts/eval.py generate --limit 5 --batch-size 1 --max-new-tokens 128
```

This reads each `user_input` from `data/eval/base_eval.jsonl`, applies the project system prompt, runs the local model at `BASE_MODEL_PATH`, and writes model responses to `outputs/baseline/`.

## 4. Run API Judge

Make sure `.env` contains:

```text
OPENAI_API_KEY=...
OPENAI_EVAL_MODEL=gpt-4o
```

If you use an OpenAI-compatible gateway, set:

```text
OPENAI_BASE_URL=https://your-compatible-endpoint/v1
```

Then run:

```bash
python scripts/eval.py judge
```

For a small smoke test:

```bash
python scripts/eval.py judge --limit 5
```

The judge writes one JSONL row per sample. Each row contains `judge_result`, the raw judge response, and any parse or API errors.

## 5. Summarize Results

```bash
python scripts/eval.py summarize
```

This creates the summary JSON and Markdown report.

## 6. Run Everything

```bash
python scripts/eval.py all
```

For the first run, prefer a small smoke test before running all 400 samples:

```bash
python scripts/eval.py all --limit 5 --batch-size 1 --max-new-tokens 128
```

After the smoke test passes, run the full evaluation:

```bash
python scripts/eval.py all
```

## 7. Important Notes

- Do not commit `.env` or API keys.
- The script uses Chat Completions for compatibility with OpenAI-compatible gateways.
- It requests JSON output through `response_format={"type": "json_object"}` and falls back automatically if the gateway does not support JSON mode.
- `--overwrite` deletes the selected output file before writing new results.
- The first baseline is evaluated under the project system prompt, so it measures the base model plus prompt behavior before SFT/DPO.


## 8. References

- OpenAI Chat Completions API reference: https://developers.openai.com/api/reference/resources/chat
- OpenAI Python SDK: https://github.com/openai/openai-python
