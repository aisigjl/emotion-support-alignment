# 中文情绪支持助手的 SFT + DPO 安全对齐

本项目构建了一个中文情绪支持场景的大模型后训练作品集：基于 Qwen3-4B-Instruct，完成项目定义、安全边界、数据蒸馏、SFT、DPO、targeted safety DPO、闭源强模型评测、误差分析和消融实验。

项目定位是**情绪支持助手**，不是心理咨询师、心理治疗系统或医疗诊断系统。模型可以提供普通情绪支持、倾听、复述和低风险建议；不能进行心理疾病诊断、治疗或药物建议；遇到自伤、自杀、伤害他人或紧急危险时，应建议用户立即联系当地紧急服务、危机热线或身边可信的人。

## 当前结果

Public eval 使用 `data/eval/public_gpt4o_distilled_eval.jsonl`，共 250 条中文情绪支持评测样本，通过 `scripts/eval.py` 调用 GPT-4o judge 评分。

| Model | Pass rate | Overall | Safety | Crisis handling | Failed |
|---|---:|---:|---:|---:|---:|
| Base | 0.9317 | 4.7912 | 4.7791 | 3.7143 | 17 |
| SFT | 0.9880 | 4.9760 | 4.9720 | 4.6818 | 3 |
| DPO general | 0.9960 | 4.9680 | 4.9880 | 4.9583 | 1 |
| DPO targeted v2 | 1.0000 | 4.9960 | 4.9960 | 5.0000 | 0 |

核心结论：SFT 主要提升基础情绪支持风格和诊断边界；DPO general 进一步提升安全性和危机处理；targeted safety DPO 在不牺牲普通支持质量的前提下，把 public eval 上的 judge violation 降为 0。

## 关键文档

- 项目定义：`docs/project_spec.md`
- 安全边界：`docs/safety_policy.md`
- 数据蒸馏流程：`docs/training_data_distillation.md`
- SFT 训练说明：`docs/sft_training.md`
- SFT 质量审计：`docs/sft_quality_review.md`
- DPO 质量审计：`docs/dpo_train_v2_quality_review.md`
- Base/SFT 评测：`docs/base_sft_evaluation.md`
- 最终消融报告：`docs/final_ablation_report.md`
- 最终 case study：`docs/final_case_studies.md`
- 技术报告：`docs/technical_report.md`
- 简历与面试材料：`docs/resume_summary.md`

## 目录结构

```text
emotion-support-alignment/
  configs/
    sft_lora_qwen3_4b.json
    dpo_lora_qwen3_4b.json
  data/
    raw/
    processed/
    eval/
  docs/
  scripts/
    train_sft.py
    train_dpo.py
    eval.py
    distill_sft_with_gpt4o.py
    distill_dpo_with_gpt4o.py
    distill_public_eval_with_gpt4o.py
  outputs/
    baseline/
    sft/
    dpo/
    eval_reports/
  README.md
```

## 模型与环境

Base model：

```text
/home/WangChanghui/wch/model/Qwen3-4B-Instruct-2507
```

Conda 环境：

```text
emotion
```

依赖安装：

```bash
pip install -r requirements.txt
```

闭源强模型评测默认使用：

```text
OPENAI_EVAL_MODEL=gpt-4o
```

## 训练入口

SFT：

```bash
CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/train_sft.py \
  --config configs/sft_lora_qwen3_4b.json
```

DPO targeted v2：

```bash
CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/train_dpo.py \
  --config configs/dpo_lora_qwen3_4b.json
```

DPO general 消融：

```bash
CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/train_dpo.py \
  --config configs/dpo_lora_qwen3_4b.json \
  --train-path data/processed/dpo_train.jsonl \
  --output-dir outputs/dpo/qwen3_4b_sft_dpo_general_lora
```

## 评测入口

DPO targeted v2 public eval：

```bash
CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/eval.py all \
  --data-path data/eval/public_gpt4o_distilled_eval.jsonl \
  --responses-path outputs/dpo/dpo_public_eval_v2_responses.jsonl \
  --judge-path outputs/dpo/dpo_public_eval_v2_judge.jsonl \
  --summary-path outputs/dpo/dpo_public_eval_v2_summary.json \
  --report-path outputs/eval_reports/dpo_public_eval_v2_report.md \
  --model-path /home/WangChanghui/wch/model/Qwen3-4B-Instruct-2507 \
  --adapter-path outputs/dpo/qwen3_4b_sft_dpo_lora \
  --model-name qwen3_4b_sft_dpo \
  --judge-model gpt-4o \
  --batch-size 1 \
  --max-new-tokens 512 \
  --overwrite
```

## 项目边界

本项目适合展示大模型后训练、数据构造、安全对齐和评测能力，不适合作为真实心理健康产品直接上线。真实应用需要专家标注、人工审核、危机响应流程、隐私合规和医疗安全评估。
