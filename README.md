# 中文情绪支持助手的 SFT + DPO 安全对齐

本项目用于构建一个大模型后训练求职作品集：围绕中文情绪支持场景，完成项目定义、安全边界、SFT、DPO、评测和报告闭环。

项目定位是情绪支持助手，不是心理咨询师、心理治疗系统或医疗诊断系统。

## 当前状态

- 已完成项目目录结构
- 已完成项目定义文档：`docs/project_spec.md`
- 已完成安全边界文档：`docs/safety_policy.md`
- 已完成 baseline 评测集：`data/eval/base_eval.jsonl`
- 已完成评测集构造说明：`docs/base_eval_construction.md`
- 已完成依赖文件：`requirements.txt`
- 已完成环境配置示例：`.env.example`
- 已完成环境安装说明：`docs/environment_setup.md`
- 已完成 baseline 生成和 API 评测脚本：`scripts/eval.py`
- 已完成评测流水线说明：`docs/eval_pipeline.md`
- 已完成公开评测数据集使用建议：`docs/public_eval_datasets.md`
- 已新增 GPT-4o 全对话蒸馏脚本：`scripts/distill_public_eval_with_gpt4o.py`
- 已新增 GPT-4o 蒸馏流程说明：`docs/gpt4o_eval_distillation.md`
- 已新增 SMILE 文件级 split 脚本：`scripts/prepare_data_split.py`
- 已生成 split manifest：`data/processed/smile_split_manifest.json`
- 已新增 SFT 蒸馏脚本：`scripts/distill_sft_with_gpt4o.py`
- 已新增 DPO 蒸馏脚本：`scripts/distill_dpo_with_gpt4o.py`
- 已新增训练数据蒸馏说明：`docs/training_data_distillation.md`
- 已新增 SFT LoRA/QLoRA 训练脚本：`scripts/train_sft.py`
- 已新增 SFT 训练配置：`configs/sft_lora_qwen3_4b.json`
- 已新增 SFT 训练说明：`docs/sft_training.md`

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

## 环境

本项目第一版 base model 使用本地路径：

```text
/home/WangChanghui/wch/model/Qwen3-4B-Instruct-2507
```

依赖安装：

```bash
pip install -r requirements.txt
```

如果误用了拼写 `requirmens.txt`，项目中也提供了兼容入口：

```bash
pip install -r requirmens.txt
```

闭源强模型评测默认预留 OpenAI API，例如：

```text
OPENAI_EVAL_MODEL=gpt-4o
```

具体安装说明见 `docs/environment_setup.md`。

## 下一步

1. 先阅读 `docs/training_data_distillation.md`，按 split manifest 分别构造 Eval/SFT/DPO 数据。
2. Eval 目标：450 条，其中 GPT-4o 蒸馏公开样本 250 条、synthetic safety 150 条、red-team 50 条。
3. SFT 目标：5000 条 `messages` 格式样本，输出到 `data/processed/sft_train.jsonl`。
4. DPO 目标：1500 对 `prompt/chosen/rejected` 偏好样本，输出到 `data/processed/dpo_train.jsonl`。
5. 蒸馏脚本支持 `--workers` 并发 API 调用，建议先用 `--workers 4`，稳定后再尝试 `--workers 8`。
6. 小样本试跑 baseline：`python scripts/eval.py all --data-path data/eval/base_eval_v2_mixed.jsonl --limit 5 --batch-size 1 --max-new-tokens 128`。
7. 确认输出无误后跑完整 baseline，并基于 judge 结果完成 `baseline_error_analysis.md`。
8. 训练 SFT 前先跑 smoke test：`CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/train_sft.py --config configs/sft_lora_qwen3_4b.json --output-dir outputs/sft/smoke_qwen3_4b_sft_lora --max-train-samples 16 --max-eval-samples 4 --eval-size 4 --max-steps 2 --overwrite-output-dir`。
9. smoke test 通过后跑完整 SFT：`CUDA_VISIBLE_DEVICES=0 conda run -n emotion python scripts/train_sft.py --config configs/sft_lora_qwen3_4b.json`。
