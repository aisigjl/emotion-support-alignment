# 简历与面试讲解材料

## 项目一句话

基于 Qwen3-4B-Instruct 构建中文情绪支持安全对齐系统，完成 SFT、DPO general、targeted safety DPO、闭源强模型评测和误差分析，使模型在共情质量和心理安全边界上相比 base model 明显提升。

## 简历描述

中文情绪支持助手安全对齐项目：基于 Qwen3-4B-Instruct 设计心理健康安全边界，使用公开 SMILE 对话经 GPT-4o/DeepSeek 蒸馏构造 5000 条 SFT 样本、1500 对 DPO 偏好数据和 300 对 targeted safety DPO 数据；采用 QLoRA 完成 SFT 与 DPO 后训练，并搭建 GPT-4o-as-judge 自动评测流水线。Public eval 上 pass rate 从 Base 93.17% 提升到 SFT 98.80%、DPO general 99.60%、targeted DPO 100.00%，crisis handling 从 3.71 提升到 5.00，最终模型在评测集中无诊断越界、药物建议、依赖诱导或危机处理违规。

## 面试讲解主线

1. **为什么做这个项目**：情绪支持是典型高安全要求中文对话场景，能体现后训练、数据构造、安全对齐和评测能力。
2. **难点是什么**：不是让模型更会安慰，而是让模型在危机、诊断、药物、AI 依赖等边界场景中稳定拒绝越界并建议现实支持。
3. **怎么构造数据**：公开对话先做文件级 split，再由强模型读完整对话后重写 SFT / DPO / Eval，避免只截取最后一轮导致语义不完整。
4. **SFT 学到了什么**：共情表达、结构化支持、低风险建议和基本安全边界。
5. **DPO 学到了什么**：在多个可行回答中更偏好安全、具体、有边界的回答。
6. **targeted DPO 为什么有价值**：它不是随机扩数据，而是根据 SFT 误差分析补危机表达、家庭安全、诊断、药物和 AI 依赖场景。
7. **怎么证明有效**：Base/SFT/DPO general/DPO targeted 四组消融，pass rate、safety、crisis handling 和 violations 均有量化结果。
8. **局限性**：GPT-4o judge 需要人工复核，public eval 安全少样本场景不足，系统不能替代心理咨询或医疗帮助。

## 可被追问的问题

**Q：为什么 DPO reference 要用 SFT adapter 而不是 base model？**

A：因为 DPO 的目标是在 SFT 已经学到的情绪支持分布上做偏好优化。如果 reference 用 base model，KL 约束会把策略拉向未对齐的 base 行为，不利于保持 SFT 风格。policy 和 reference 都从 SFT adapter 初始化，reference 冻结，才能让 DPO 学到“在 SFT 能力基础上偏好更安全回答”。

**Q：targeted safety DPO 和普通 DPO 的区别是什么？**

A：普通 DPO 主要覆盖通用共情、建议质量和边界；targeted safety DPO 直接针对误差分析发现的剩余问题，比如危机升级不明确、药物建议、诊断边界、AI 依赖和家庭安全。实验上 DPO general pass rate 为 99.60%，targeted v2 达到 100.00%，并修复了 DPO general 的一个低风险退化样本。

**Q：为什么不用人工标注？**

A：这个项目定位是求职作品集，目标是低成本构建完整后训练闭环。强模型蒸馏可以快速得到高质量初版数据，但关键样本仍需要抽检和规则审计。真实产品阶段应该引入专家标注和人工复核。

**Q：这个模型能用于心理咨询吗？**

A：不能。项目明确限定为情绪支持助手，不做诊断、治疗或药物建议。高风险场景必须建议联系紧急资源、专业人士或可信现实支持。
