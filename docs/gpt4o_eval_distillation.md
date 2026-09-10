# GPT-4o Full-Dialogue Eval Distillation

## 1. Goal

This workflow uses GPT-4o to read each selected SMILE JSON dialogue and distill it into self-contained Chinese evaluation samples.

It replaces the earlier mechanical approach:

```text
last user turn + recent 2-4 turns of context
```

with a stronger process:

```text
full public dialogue
  -> GPT-4o understands the complete emotional situation
  -> GPT-4o rewrites an anonymized, self-contained user_input
  -> local script standardizes scenario/risk/expected/forbidden labels
  -> base model generates responses
  -> GPT-4o judge evaluates model responses
```

This is more suitable for the project because the model under evaluation receives a natural standalone user expression instead of a fragment that depends on hidden dialogue history.

## 2. Input And Output

Input files:

```text
data/raw/smile/*.json
```

Distilled public eval output:

```text
data/eval/public_gpt4o_distilled_eval.jsonl
```

Mixed eval output:

```text
data/eval/base_eval_v2_mixed.jsonl
```

The mixed eval combines:

| Component | Default Count | Purpose |
|---|---:|---|
| GPT-4o distilled SMILE public samples | 250 | Natural Chinese emotional support expressions |
| Synthetic safety subset | 150 | Fixed diagnosis/crisis/medication/dependency regression |
| Hand-written red-team samples | 50 | Hard boundary tests |

## 3. Distilled Sample Schema

Each public distilled row has the same core eval schema as `base_eval.jsonl`, with two extra fields:

```json
{
  "id": "gpt4o_smile_000001",
  "source": "gpt4o_distilled_smile",
  "scenario": "self_denial",
  "risk_level": "medium",
  "user_input": "自包含的中文来访者表达",
  "conversation_summary": "GPT-4o 从完整对话提炼的背景摘要",
  "expected_behavior": ["emotion_reflection", "validation", "open_question"],
  "forbidden_behavior": ["diagnosis", "medical_advice", "dependency_inducing"],
  "judge_notes": "评测注意点",
  "source_metadata": {
    "raw_file": "data/raw/smile/35.json",
    "distiller_model": "gpt-4o",
    "distillation_method": "full_dialogue_read_then_rewrite_self_contained_eval_sample"
  }
}
```

`conversation_summary` is not raw history. It is a compact background extracted from the whole file, so the baseline model can understand why the current expression matters without seeing the original public dialogue.

## 4. Commands

First check that local SMILE files can be found without calling the API:

```bash
python scripts/distill_public_eval_with_gpt4o.py --dry-run --max-files 10
```

Run a tiny API smoke test:

```bash
python scripts/distill_public_eval_with_gpt4o.py   --target-count 6   --max-files 10   --samples-per-file 2   --allow-partial   --build-mixed   --public-count 6   --synthetic-count 6   --redteam-count 4   --overwrite
```

Build the recommended 450-sample mixed eval set:

```bash
python scripts/distill_public_eval_with_gpt4o.py   --target-count 250   --max-files 400   --samples-per-file 2   --build-mixed   --public-count 250   --synthetic-count 150   --redteam-count 50
```

If proxy variables interfere with API access, run the same command with proxy variables cleared:

```bash
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY   python scripts/distill_public_eval_with_gpt4o.py --target-count 250 --max-files 400 --samples-per-file 2 --build-mixed
```

Then evaluate the base model on the mixed set:

```bash
python scripts/eval.py all   --data-path data/eval/base_eval_v2_mixed.jsonl   --limit 5   --batch-size 1   --max-new-tokens 128
```

After smoke testing, remove `--limit 5` to run the full baseline.

## 5. Quality Control

Before treating the dataset as fixed, manually inspect at least 30 distilled rows:

```bash
sed -n '1,30p' data/eval/public_gpt4o_distilled_eval.jsonl
```

Check these points:

- `user_input` should sound natural and self-contained.
- It should not expose names, phone numbers, addresses, schools, companies, or exact private identifiers.
- `scenario` and `risk_level` should match the emotional and safety signal.
- Crisis, medication, diagnosis, family safety, and AI dependency cases must be labeled conservatively.
- `reference_response` is only an optional safe example, not a strict gold answer.

## 6. Cost And Scope

SMILE contains many JSON files. Running GPT-4o over every file can be expensive and slow. For this portfolio project, the recommended target is 200-300 public distilled eval samples, then combine them with synthetic safety and red-team samples to reach 400-500 total samples.

The script supports all-file processing by using `--max-files 0`, but start with small runs and inspect quality first.

## 7. OpenAI API Notes

The script uses the OpenAI Python SDK with Chat Completions and JSON-object output when the configured API endpoint supports it. If the gateway does not support JSON mode, the script automatically retries without `response_format` and parses the JSON object from text.

Relevant official OpenAI documentation:

- OpenAI Chat Completions API: https://platform.openai.com/docs/api-reference/chat/create
- OpenAI Python SDK: https://github.com/openai/openai-python


## 8. Recommended Sample Counts

You do not need to distill the full SMILE dataset for this project. A fixed, high-quality, stratified eval set is more useful than a very large weakly audited set.

Recommended final size:

```text
GPT-4o distilled public SMILE samples: 200-300
Synthetic safety regression samples:   120-150
Hand-written red-team samples:          40-60
Total:                                400-500
```

For the first formal version, use this target:

```text
public_count=250
synthetic_count=150
redteam_count=50
total=450
```

This is enough for a portfolio-grade base/SFT/DPO comparison because each major scenario can have about 30-60 examples. Bigger is only useful after the label quality, scenario balance, and judge rubric are already stable.

Suggested iteration order:

```text
20-30 samples: smoke test and manual quality check
100-150 samples: pilot baseline and prompt/rubric debugging
400-500 samples: fixed final eval set for base/SFT/DPO comparison
500-800 samples: optional robustness expansion
```

Avoid processing all SMILE files unless you are building a larger benchmark. Full-dataset distillation is slower, costs more API calls, and makes manual auditing harder.

## 9. Resume And Retry

The distillation script supports checkpoint-style resume by default.

It writes rows incrementally to:

```text
data/eval/public_gpt4o_distilled_eval.jsonl
```

It also writes a processed-file log to:

```text
data/eval/public_gpt4o_distilled_processed.jsonl
```

If the command is interrupted, run the same command again. The script reads existing output rows and the processed log, skips completed raw files, and continues until `--target-count` is reached.

Use normal resume after an interruption:

```bash
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY   python scripts/distill_public_eval_with_gpt4o.py   --target-count 250   --max-files 400   --samples-per-file 2   --build-mixed   --public-count 250   --synthetic-count 150   --redteam-count 50
```

If earlier attempts failed because of network or API errors, retry failed raw files too:

```bash
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY   python scripts/distill_public_eval_with_gpt4o.py   --target-count 250   --max-files 400   --samples-per-file 2   --build-mixed   --public-count 250   --synthetic-count 150   --redteam-count 50   --retry-errors
```

Only use `--overwrite` when you intentionally want to delete previous distilled outputs and rebuild the dataset from scratch.
