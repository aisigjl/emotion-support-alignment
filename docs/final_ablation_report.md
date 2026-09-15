# 最终消融实验报告：中文情绪支持助手安全对齐

## 实验目的

本报告用于回答一个核心问题：在中文情绪支持场景中，SFT、通用 DPO、targeted safety DPO 分别带来了什么收益。

对比模型如下：

| 变体 | 训练来源 | 说明 |
|---|---|---|
| Base | `/home/WangChanghui/wch/model/Qwen3-4B-Instruct-2507` | 未经过本项目后训练的 base instruct 模型 |
| SFT | `outputs/sft/qwen3_4b_sft_lora` | 使用 5000 条 GPT-4o/DeepSeek 蒸馏中文情绪支持样本做 LoRA/QLoRA SFT |
| DPO general | `outputs/dpo/qwen3_4b_sft_dpo_general_lora` | 从 SFT 出发，使用原始 1500 对通用 DPO 偏好数据训练 |
| DPO targeted v2 | `outputs/dpo/qwen3_4b_sft_dpo_lora` | 从 SFT 出发，使用 1500 对通用 DPO + 300 对 targeted safety DPO 训练 |

评测使用 `data/eval/public_gpt4o_distilled_eval.jsonl`，共 250 条中文 public eval 样本，由 `scripts/eval.py` 调用 GPT-4o judge 评分。Base 有 1 条 judge parse/error，因此有效样本为 249；其余模型均为 250 条有效样本。

## 总体结果

| Model | Valid | Pass rate | Overall | Empathy | Support | Safety | Crisis | Failed | Violations |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Base | 249 | 0.9317 | 4.7912 | 4.9759 | 4.7912 | 4.7791 | 3.7143 | 17 | 25 |
| SFT | 250 | 0.9880 | 4.976 | 5 | 4.976 | 4.972 | 4.6818 | 3 | 3 |
| DPO general | 250 | 0.9960 | 4.968 | 4.988 | 4.964 | 4.988 | 4.9583 | 1 | 3 |
| DPO targeted v2 | 250 | 1.0000 | 4.996 | 5 | 4.996 | 4.996 | 5 | 0 | 0 |

关键观察：

- SFT 相比 Base：pass rate 从 0.9317 提升到 0.9880，主要修复诊断越界、危机弱处理和依赖诱导问题。
- DPO general 相比 SFT：pass rate 从 0.9880 提升到 0.9960，safety 从 4.9720 提升到 4.9880，crisis handling 从 4.6818 提升到 4.9583。
- DPO targeted v2 相比 DPO general：pass rate 从 0.9960 提升到 1.0000，overall 从 4.9680 提升到 4.9960，crisis handling 达到 5.0000，并且 judge violation 为 0。

## 按风险等级拆解

| Risk level | Base | SFT | DPO general | DPO targeted v2 |
|---|---:|---:|---:|---:|
| low | 170/171 (99.4%) | 171/171 (100.0%) | 170/171 (99.4%) | 171/171 (100.0%) |
| medium | 50/57 (87.7%) | 57/57 (100.0%) | 57/57 (100.0%) | 57/57 (100.0%) |
| high | 11/20 (55.0%) | 18/21 (85.7%) | 21/21 (100.0%) | 21/21 (100.0%) |
| disallowed | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) |

高风险样本是最能体现安全对齐收益的部分：Base 在 high-risk 样本上只有 55.0% pass rate；SFT 提升到 85.7%；DPO general 和 targeted v2 均达到 100%。targeted v2 的额外价值主要体现在把 overall、support 和 crisis handling 进一步拉满，同时避免 DPO general 在低风险样本上的单点退化。

## 按关键场景拆解

| Scenario | Base | SFT | DPO general | DPO targeted v2 |
|---|---:|---:|---:|---:|
| crisis_expression | 7/13 (53.8%) | 11/13 (84.6%) | 13/13 (100.0%) | 13/13 (100.0%) |
| diagnosis_request | 3/7 (42.9%) | 7/7 (100.0%) | 7/7 (100.0%) | 7/7 (100.0%) |
| family_safety | 3/6 (50.0%) | 5/6 (83.3%) | 6/6 (100.0%) | 6/6 (100.0%) |
| interpersonal_relationship | 70/73 (95.9%) | 73/73 (100.0%) | 72/73 (98.6%) | 73/73 (100.0%) |
| pressure_stress | 47/48 (97.9%) | 48/48 (100.0%) | 48/48 (100.0%) | 48/48 (100.0%) |
| ai_dependency | 2/2 (100.0%) | 2/2 (100.0%) | 2/2 (100.0%) | 2/2 (100.0%) |
| medication_request | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) | 1/1 (100.0%) |

关键结论：

- `crisis_expression`：Base 只有 7/13 通过，SFT 提升到 11/13，DPO 两个版本均为 13/13。
- `diagnosis_request`：Base 只有 3/7 通过，SFT 后达到 7/7，说明 SFT 已经显著学到“拒绝诊断 + 建议专业评估”的边界。
- `family_safety`：Base 3/6，SFT 5/6，DPO 后 6/6，说明 DPO 对安全优先、现实支持和升级建议有明显补充。
- `interpersonal_relationship`：DPO general 出现 1 个低风险支持质量退化样本，而 targeted v2 修复到 73/73。

## 违规与禁忌行为

| Model | Top violations / forbidden behavior |
|---|---|
| Base | diagnosis_given=5, diagnosis_attempt=3, insufficient_safety_focus=2, inadequate_crisis_escalation=2, possible_missing_crisis_escalation=2, forbidden:diagnosis=8, forbidden:crisis_minimization=3, forbidden:normal_chat_continuation=3, forbidden:dependency_inducing=2, forbidden:unsafe_confrontation=2 |
| SFT | possible_missing_crisis_escalation=2, insufficient_safety_focus=1 |
| DPO general | lack_of_clarity=1, poor_empathy=1, unhelpful_support=1, forbidden:dismissive_response=1 |
| DPO targeted v2 | None |

Base 的主要问题是诊断越界、危机处理不足、依赖诱导和风险淡化。SFT 已经消除了大部分 forbidden behavior，但仍残留高风险场景下安全升级不够明确的问题。DPO general 进一步压低违规，但出现 1 条低风险场景支持质量退化。DPO targeted v2 在该 public eval 上没有 judge violations 或 forbidden behavior。

## 消融结论

1. **SFT 是基础能力阶段**：它把 base model 从通用聊天风格拉到稳定的情绪支持风格，显著降低诊断越界和危机弱处理。
2. **DPO general 是偏好对齐阶段**：它进一步提升安全分和危机处理分，说明偏好数据能让模型更稳定地选择安全、具体、有边界的回答。
3. **targeted safety DPO 是安全补强阶段**：在通用 DPO 的基础上加入 300 对 targeted safety preference pairs 后，模型在 public eval 上达到 250/250 pass，并修复 DPO general 的单点低风险退化。
4. **最合理的项目结论**：targeted safety DPO 没有只是“多训一点数据”，而是针对 SFT 误差分析暴露出的高风险安全升级不足进行定向补强，因此能在危机表达、家庭安全、诊断边界等场景中获得更稳的行为。

## 局限性

- 本报告使用 public eval 250 条结果，没有纳入 mixed eval 的 449 条安全增强评测；因此 medication_request 和 ai_dependency 等少样本场景不能过度解读。
- GPT-4o judge 是强模型评测，不等价于临床安全认证；它适合做项目评估和相对比较，但不能作为真实心理健康产品上线依据。
- targeted DPO v2 仍有 2 条 rule flags，其中 1 条是 family safety 场景的危机升级提示不够显式，后续可以作为下一轮数据增强方向。
- 本项目定位是中文情绪支持助手，不是心理咨询、治疗、诊断或药物建议系统。

## 可写入简历的结论

基于 Qwen3-4B-Instruct 构建中文情绪支持安全对齐系统，完成 SFT、DPO general 和 targeted safety DPO 消融。Public eval 上，pass rate 从 Base 93.17% 提升到 SFT 98.80%、DPO general 99.60%、targeted DPO 100.00%；crisis handling 从 3.71 提升到 5.00；诊断越界、依赖诱导和危机处理违规在最终模型中降为 0。
