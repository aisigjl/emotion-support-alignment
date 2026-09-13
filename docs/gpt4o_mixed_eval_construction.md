# GPT-4o Distilled Mixed Eval Dataset

## Output

This document describes `data/eval/base_eval_v2_mixed.jsonl` when built through `scripts/distill_public_eval_with_gpt4o.py`.

Total samples: 449

## Construction

The mixed eval set combines three parts:

1. Public SMILE/SmileChat dialogues distilled by GPT-4o into self-contained Chinese eval samples.
2. A synthetic safety subset from `data/eval/base_eval.jsonl`.
3. Hand-written red-team prompts for diagnosis, crisis, medication, family safety, AI dependency, and self-denial boundaries.

The public component is not a last-turn extraction. GPT-4o reads each selected full dialogue, summarizes the emotional situation, anonymizes the content, and rewrites it into an evaluation prompt that can stand alone.

## Source Counts

| Source | Count |
|---|---:|
| `gpt4o_distilled_smile` | 250 |
| `synthetic_eval_seed_v1_safety_subset` | 150 |
| `synthetic_redteam_v1` | 49 |

## Scenario Counts

| Scenario | Count |
|---|---:|
| `ai_dependency` | 24 |
| `crisis_expression` | 63 |
| `diagnosis_request` | 45 |
| `family_safety` | 22 |
| `interpersonal_relationship` | 74 |
| `loneliness` | 16 |
| `medication_request` | 39 |
| `ordinary_emotion` | 54 |
| `pressure_stress` | 50 |
| `public_emotional_support_dialogue` | 1 |
| `self_denial` | 61 |

## Risk Counts

| Risk Level | Count |
|---|---:|
| `disallowed` | 39 |
| `high` | 87 |
| `low` | 176 |
| `medium` | 147 |

## Data Fields

Each distilled public row includes:

- `user_input`: self-contained current user expression.
- `conversation_summary`: distilled background from the full dialogue.
- `expected_behavior`: standardized project behavior tags.
- `forbidden_behavior`: standardized safety boundary tags.
- `source_metadata.raw_file`: original local SMILE JSON path.
- `source_metadata.distillation_method`: full-dialogue read and rewrite method.

## Usage

Run a small smoke test first:

```bash
python scripts/distill_public_eval_with_gpt4o.py --target-count 6 --max-files 10 --samples-per-file 2 --allow-partial --build-mixed --public-count 6 --synthetic-count 6 --redteam-count 4 --overwrite
```

Build a 450-sample mixed eval set:

```bash
python scripts/distill_public_eval_with_gpt4o.py --target-count 250 --max-files 400 --samples-per-file 2 --build-mixed --public-count 250 --synthetic-count 150 --redteam-count 50
```

Then run baseline evaluation:

```bash
python scripts/eval.py all --data-path data/eval/base_eval_v2_mixed.jsonl --limit 5 --batch-size 1 --max-new-tokens 128
```

## Notes

This dataset is evaluation-only. Do not use it for SFT or DPO training unless you create a separate training split and perform an explicit leakage audit.
