# 技术报告：中文情绪支持助手的 SFT + DPO 安全对齐

## 摘要

本项目围绕中文情绪支持场景，基于 Qwen3-4B-Instruct 构建一个有安全边界的情绪支持助手。项目完整覆盖项目定义、安全边界、数据蒸馏、SFT、DPO、targeted safety DPO、闭源强模型评测、误差分析和消融实验。

最终 public eval 结果显示：Base pass rate 为 0.9317，SFT 为 0.9880，DPO general 为 0.9960，targeted DPO v2 为 1.0000；crisis handling 从 Base 的 3.7143 提升到最终模型的 5.0000。

## 任务定义

模型定位为中文情绪支持助手，只提供倾听、复述、普通情绪支持和低风险建议。模型不能执行以下行为：

- 心理疾病诊断或替代专业评估。
- 心理治疗、治疗计划或疗效承诺。
- 药物名称、剂量、停药、换药或自行用药建议。
- 强化用户对 AI 的依赖。
- 在自伤、自杀、伤害他人、家庭暴力等高风险场景中继续普通陪聊而不做安全升级。

安全边界见 `docs/safety_policy.md`。

## 数据构造

| 数据 | 规模 | 用途 |
|---|---:|---|
| SFT train | 5000 条 | 训练情绪支持基本风格、共情表达和边界回复 |
| DPO general | 1500 对 | 通用偏好优化，提升回答质量和边界稳定性 |
| targeted safety DPO | 300 对 | 针对 SFT 误差分析中的危机表达、家庭安全、诊断、药物、AI 依赖进行补强 |
| public eval | 250 条 | 本报告使用的最终对比评测集 |
| mixed eval | 449 条 | 已构造但本轮报告按用户决策跳过 |

SFT/DPO 数据来自公开 SMILE 对话的文件级 split，并经强模型读完整对话后重写为训练样本。Eval split 与训练 split 在 raw file 级别隔离，避免数据泄漏。

## 训练流程

1. **Base**：`/home/WangChanghui/wch/model/Qwen3-4B-Instruct-2507`。
2. **SFT**：QLoRA，5000 条蒸馏样本，assistant-only loss，输出 `outputs/sft/qwen3_4b_sft_lora`。
3. **DPO general**：从 SFT adapter 出发，使用原始 1500 对 DPO，输出 `outputs/dpo/qwen3_4b_sft_dpo_general_lora`。
4. **DPO targeted v2**：从 SFT adapter 出发，使用 1500 对原始 DPO + 300 对 targeted safety DPO，输出 `outputs/dpo/qwen3_4b_sft_dpo_lora`。

DPO 训练中，policy 和 reference 均加载同一个 SFT adapter，reference 冻结，使偏好优化发生在 SFT 行为基础上。

## 评测方法

评测由 `scripts/eval.py` 完成：

1. 本地模型生成回复。
2. 调用 GPT-4o judge，按共情、支持策略、安全边界、危机处理评分。
3. 规则脚本额外检测诊断、药物建议、依赖诱导、危机升级缺失等 flags。
4. 输出 summary JSON 和 Markdown report。

本报告主要使用 public eval 250 条结果，路径如下：

- Base: `outputs/baseline/public_eval_v2_summary.json`
- SFT: `outputs/sft/sft_eval_v2_summary.json`
- DPO general: `outputs/dpo/dpo_general_public_eval_v2_summary.json`
- DPO targeted v2: `outputs/dpo/dpo_public_eval_v2_summary.json`

## 实验结果

| Model | Valid | Pass rate | Overall | Empathy | Support | Safety | Crisis | Failed | Violations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Base | 249 | 0.9317 | 4.7912 | 4.9759 | 4.7912 | 4.7791 | 3.7143 | 17 | 25 |
| SFT | 250 | 0.9880 | 4.976 | 5 | 4.976 | 4.972 | 4.6818 | 3 | 3 |
| DPO general | 250 | 0.9960 | 4.968 | 4.988 | 4.964 | 4.988 | 4.9583 | 1 | 3 |
| DPO targeted v2 | 250 | 1.0000 | 4.996 | 5 | 4.996 | 4.996 | 5 | 0 | 0 |

风险等级结果：

| Risk level | Base | SFT | DPO general | DPO targeted v2 |
|---|---:|---:|---:|---:|
| low | 170/171 (99.4%) | 171/171 (100.0%) | 170/171 (99.4%) | 171/171 (100.0%) |
| medium | 50/57 (87.7%) | 57/57 (100.0%) | 57/57 (100.0%) | 57/57 (100.0%) |
| high | 11/20 (55.0%) | 18/21 (85.7%) | 21/21 (100.0%) | 21/21 (100.0%) |
| disallowed | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) |

关键场景结果：

| Scenario | Base | SFT | DPO general | DPO targeted v2 |
|---|---:|---:|---:|---:|
| crisis_expression | 7/13 (53.8%) | 11/13 (84.6%) | 13/13 (100.0%) | 13/13 (100.0%) |
| diagnosis_request | 3/7 (42.9%) | 7/7 (100.0%) | 7/7 (100.0%) | 7/7 (100.0%) |
| family_safety | 3/6 (50.0%) | 5/6 (83.3%) | 6/6 (100.0%) | 6/6 (100.0%) |
| interpersonal_relationship | 70/73 (95.9%) | 73/73 (100.0%) | 72/73 (98.6%) | 73/73 (100.0%) |
| pressure_stress | 47/48 (97.9%) | 48/48 (100.0%) | 48/48 (100.0%) | 48/48 (100.0%) |
| ai_dependency | 2/2 (100.0%) | 2/2 (100.0%) | 2/2 (100.0%) | 2/2 (100.0%) |
| medication_request | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) |

详细消融分析见 `docs/final_ablation_report.md`，典型样本见 `docs/final_case_studies.md`。

## 主要结论

- SFT 负责把模型从通用问答风格拉到稳定的中文情绪支持风格。
- 通用 DPO 进一步提高安全性和危机处理，尤其修复 SFT 在高风险表达中安全升级不够明确的问题。
- targeted safety DPO 通过针对性构造偏好对，使最终模型在 public eval 上达到 250/250 pass，并修复 DPO general 的低风险单点退化。
- 最终模型仍不能被视为心理咨询或医疗产品，只能作为安全边界明确的情绪支持助手研究 demo。

## 局限性与后续工作

- Public eval 中 medication_request 和 ai_dependency 样本很少，应在后续 mixed eval 或 red-team eval 中扩大覆盖。
- GPT-4o judge 适合相对比较，但仍需要人工复核关键高风险样本。
- targeted DPO v2 仍有 rule flags，尤其 family safety 场景中“明确危机升级路径”可以继续补强。
- Demo 阶段应加入安全免责声明和高风险触发提示，避免用户误认为系统能替代专业帮助。

## 复现实验入口

SFT 训练：

```bash
CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/train_sft.py \
  --config configs/sft_lora_qwen3_4b.json
```

DPO targeted v2 训练：

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
