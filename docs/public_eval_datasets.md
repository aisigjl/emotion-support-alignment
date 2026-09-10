# Public Datasets for Emotion Support Evaluation

## 1. Why Public Datasets Are Needed

The current `data/eval/base_eval.jsonl` is a synthetic coverage set. It is useful for safety regression because it deliberately covers diagnosis requests, crisis expressions, medication requests, AI dependency, and family safety risks.

Its weakness is also clear: many samples are generated from templates, so they do not fully represent natural user language.

The recommended approach is not to replace it completely. Use a two-layer evaluation design:

```text
Layer 1: synthetic safety eval
  - fixed regression set
  - covers rare but important boundary cases
  - used for every base/SFT/DPO comparison

Layer 2: public natural eval
  - sampled from public datasets
  - covers more natural phrasing and dialogue distribution
  - used to test whether the model works beyond templates
```

## 2. Recommended Public Datasets

| Dataset | Language | Best Use | Notes |
|---|---|---|---|
| `PsyQA` | Chinese | Psychological support QA eval and SFT reference | Strong fit for Chinese; full data access may require following the authors' release procedure. |
| `SMILE` / SmileChat | Chinese | Chinese mental health support dialogue eval and SFT | Useful for natural Chinese support dialogues; many samples are generated or expanded, so keep a held-out eval split. |
| `CPsyCounD` / CPsyCoun | Chinese | Multi-turn counseling-style evaluation | More counseling-like; use cautiously because this project should not claim therapy capability. |
| `SoulChatCorpus` | Chinese | Large-scale empathy/support SFT reference | Large and useful, but more suitable for training than fixed eval unless carefully sampled. |
| `ESConv` | English | Support-strategy taxonomy and optional translated eval | Has explicit emotional support strategies; not directly Chinese unless translated. |
| `EmpatheticDialogues` | English | Empathy response evaluation and optional translated eval | Good for empathy, less focused on mental health safety. |

## 3. Dataset Details

### 3.1 PsyQA

Use case:

- Chinese psychological support QA.
- Good for evaluating whether the model gives helpful, non-diagnostic, non-overreaching support.
- Useful for SFT after removing unsafe or overly clinical content.

Recommended eval conversion:

```json
{
  "id": "public_psyqa_000001",
  "source": "psyqa",
  "scenario": "public_psychological_qa",
  "risk_level": "medium",
  "user_input": "original question",
  "reference_response": "original high-quality answer if available",
  "expected_behavior": ["emotion_reflection", "boundary_setting", "professional_referral_if_needed"],
  "forbidden_behavior": ["diagnosis", "medical_advice", "treatment_plan"]
}
```

Practical note:

- Do not directly treat original answers as always safe. Some may be too counseling-like for this project's boundary.
- Keep the public eval split separate from any SFT/DPO training split.

### 3.2 SMILE / SmileChat

Use case:

- Chinese mental health support dialogue.
- Good for reducing the template feeling in eval.
- Suitable for extracting single-turn or multi-turn user queries.

Recommended eval conversion:

```json
{
  "id": "public_smile_000001",
  "source": "smile",
  "scenario": "public_emotional_support_dialogue",
  "risk_level": "low_or_medium",
  "conversation_context": ["previous turns if needed"],
  "user_input": "current user turn",
  "reference_response": "assistant/supporter turn if available",
  "expected_behavior": ["emotion_reflection", "paraphrase", "open_question", "gentle_suggestion"],
  "forbidden_behavior": ["diagnosis", "medical_advice", "dependency_inducing"]
}
```

Practical note:

- Prefer natural user turns over generated-looking assistant turns when building eval.
- If using it for training, reserve a non-overlapping split for evaluation.

### 3.3 CPsyCounD / CPsyCoun

Use case:

- Chinese multi-turn psychological counseling style conversations.
- Useful for testing multi-turn context handling.
- Useful for identifying whether a model becomes too clinical or too directive.

Project boundary:

- This project is not a therapy or counseling product.
- Use CPsyCoun-like data mainly for evaluation or careful SFT, not for claiming clinical counseling ability.

Recommended eval conversion:

```json
{
  "id": "public_cpsycoun_000001",
  "source": "cpsycoun",
  "scenario": "public_multiturn_support",
  "risk_level": "medium",
  "conversation_context": ["turn 1", "turn 2"],
  "user_input": "latest user turn",
  "expected_behavior": ["emotion_reflection", "open_question", "boundary_setting"],
  "forbidden_behavior": ["diagnosis", "treatment_plan", "medical_advice"]
}
```

### 3.4 SoulChatCorpus

Use case:

- Large-scale Chinese empathy/support conversation corpus.
- More useful for SFT data construction than baseline eval.

Risks:

- Large corpora may contain style drift, repetitive comfort language, or unsafe boundary examples.
- If used for training, run safety filters and manual sampling before inclusion.

### 3.5 ESConv

Use case:

- Emotional support conversation dataset with support strategy annotations.
- Good for learning support strategy taxonomy.
- Useful for translated eval if you want to test strategy use in Chinese.

Typical strategies include:

- question
- restatement or paraphrasing
- reflection of feelings
- self-disclosure
- affirmation and reassurance
- providing suggestions
- information support
- others

Practical note:

- Since this project is Chinese-first, ESConv is better as a strategy reference or translated subset, not the main eval source.

### 3.6 EmpatheticDialogues

Use case:

- Open-domain empathy response data.
- Good for broad empathy and emotion recognition.

Limitations:

- It is English.
- It is not specifically designed for mental health safety.
- It does not sufficiently cover diagnosis, medication, crisis, or dependency boundaries.

## 4. Recommended Eval Set v2 Design

Replace the current single synthetic eval with a combined eval set:

| Component | Count | Source | Purpose |
|---|---:|---|---|
| Synthetic safety eval | 200 | current synthetic set | Fixed safety boundary regression |
| Public Chinese natural eval | 200 | PsyQA/SMILE/CPsyCoun/SoulChat sampled split | Natural wording and realistic scenarios |
| Public or translated empathy eval | 50 | ESConv/EmpatheticDialogues translated subset | Strategy and empathy coverage |
| Red-team safety eval | 50 | synthetic, hand-written | Hard diagnosis/crisis/medication/dependency cases |

Total recommended size:

```text
400-500 samples
```

This is stronger than the current 400 synthetic samples because it combines natural distribution and targeted safety coverage.

## 5. Practical Next Step

Create a second evaluation file instead of overwriting v1:

```text
data/eval/base_eval_v1_synthetic.jsonl
  - keep current 400 synthetic samples

data/eval/base_eval_v2_mixed.jsonl
  - 200 synthetic safety samples
  - 200 public Chinese samples
  - 50 translated empathy samples
  - 50 red-team samples
```

For the next implementation step, write a converter script:

```text
scripts/prepare_public_eval.py
```

The script should:

1. Load public dataset files from `data/raw/`.
2. Normalize them into the project eval schema.
3. Deduplicate similar user inputs.
4. Assign `scenario` and `risk_level`.
5. Write `data/eval/base_eval_v2_mixed.jsonl`.
6. Write a split manifest to avoid train/eval leakage.

## 6. Public Dataset Handling Rules

- Always keep license and source metadata.
- Do not mix eval samples into SFT or DPO training.
- Do not blindly trust original answers as safe labels.
- Run the project safety policy over public assistant responses before using them as references.
- For English datasets, translated samples should be marked with `translated_from`.
- Preserve a fixed eval version so base/SFT/DPO comparisons remain fair.


## 8. Are Dialogue Records Useful?

Yes, dialogue records are useful, but they should not be used as exact-answer evaluation data.

For this project, public dialogue datasets are useful in three ways:

1. Natural user language: they provide realistic expressions of stress, loneliness, relationship conflict, self-denial, and emotional distress. This fixes the template-like weakness of synthetic eval samples.
2. Multi-turn context: they let us test whether the model can respond to a user's latest message while respecting previous context.
3. SFT reference: high-quality assistant/supporter turns can be used as SFT examples after safety filtering.

They should not be used this way:

- Do not compare the model output against the original assistant response using exact match or BLEU/ROUGE as the main metric.
- Do not assume the original assistant response is always safe, professional, or aligned with this project's boundary.
- Do not mix the same conversation into both training and evaluation.
- Do not treat counseling-style data as proof that the model can provide therapy.

Earlier baseline conversion:

```text
conversation records
  -> extract last user turn
  -> keep recent 2-4 turns as conversation_context
```

This is useful as a quick baseline, but it is not the preferred version for this project because many last turns depend on hidden context.

Preferred eval conversion now:

```text
conversation records
  -> GPT-4o reads the full dialogue file
  -> GPT-4o summarizes the whole emotional situation and safety signal
  -> GPT-4o rewrites an anonymized, self-contained user_input
  -> local script standardizes scenario/risk/expected/forbidden labels
  -> ask base/SFT/DPO model to answer
  -> use GPT-4o/API judge with the project rubric
  -> compare model versions by scores and violation rates
```

So, for baseline evaluation, dialogue datasets mainly provide natural situations and language distribution. The original assistant reply is only a `reference_response` for human inspection, not a strict gold answer. The implementation is documented in `docs/gpt4o_eval_distillation.md`.

## 9. References

- ESConv GitHub: https://github.com/thu-coai/Emotional-Support-Conversation
- EmpatheticDialogues GitHub: https://github.com/facebookresearch/EmpatheticDialogues
- PsyQA paper page: https://huggingface.co/papers/2106.01702
- SMILE GitHub: https://github.com/qiuhuachuan/smile
- CPsyCoun / CPsyCounD paper page: https://arxiv.org/abs/2405.16433
- SoulChatCorpus ModelScope page: https://modelscope.cn/datasets/YIRONGCHEN/SoulChatCorpus
