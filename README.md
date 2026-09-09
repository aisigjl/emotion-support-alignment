# 中文情绪支持助手的 SFT + DPO 安全对齐

本项目用于构建一个大模型后训练求职作品集：围绕中文情绪支持场景，完成项目定义、安全边界、SFT、DPO、评测和报告闭环。

项目定位是情绪支持助手，不是心理咨询师、心理治疗系统或医疗诊断系统。

## 当前状态

- 已完成项目目录结构
- 已完成项目定义文档：`docs/project_spec.md`
- 已完成安全边界文档：`docs/safety_policy.md`
- 已完成 baseline 评测集：`data/eval/base_eval.jsonl`
- 已完成评测集构造说明：`docs/base_eval_construction.md`

## 目录结构

```text
emotion-support-alignment/
  data/
    raw/
    processed/
    eval/
  configs/
  scripts/
  outputs/
    baseline/
    sft/
    dpo/
    eval_reports/
  demo/
  docs/
    project_spec.md
    safety_policy.md
  README.md
```

## 下一步

1. 跑 base model，生成 `outputs/baseline/base_responses.jsonl`。
2. 编写规则检测和人工抽样评审脚本。
3. 完成第一版 `baseline_error_analysis.md`。
