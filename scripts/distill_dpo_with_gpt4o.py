from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import random
import re
import sys
import time
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.config import OPENAI_EVAL_MODEL, OPENAI_MAX_RETRIES, OPENAI_REQUEST_SLEEP, SEED  # noqa: E402
from scripts.distill_public_eval_with_gpt4o import (  # noqa: E402
    ALLOWED_RISK_LEVELS,
    ALLOWED_SCENARIOS,
    anonymize_text,
    append_jsonl,
    build_openai_client,
    coerce_list,
    create_chat_completion_with_retry,
    discover_raw_files,
    extract_json_object,
    file_sha256,
    format_dialogue_for_prompt,
    is_minimally_usable,
    load_turns,
    normalize_scenario_and_risk,
    processed_raw_files,
    project_path,
    read_jsonl,
    role_counts,
    truncate_text,
)
from scripts.eval import BASE_ASSISTANT_SYSTEM_PROMPT, detect_rule_flags  # noqa: E402
from scripts.prepare_data_split import DEFAULT_MANIFEST_PATH, load_split_files, relative_to_project  # noqa: E402
from scripts.prepare_public_eval import CREATED_AT, SMILE_SOURCE_PAGE, normalize_text, text_hash, write_json, write_jsonl  # noqa: E402

DPO_OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "dpo_train.jsonl"
DPO_SUMMARY_PATH = PROJECT_ROOT / "data" / "processed" / "dpo_train_summary.json"
DPO_PROCESSED_LOG_PATH = PROJECT_ROOT / "data" / "processed" / "dpo_distilled_processed.jsonl"

DPO_DISTILLER_SYSTEM_PROMPT = """你是中文情绪支持助手 DPO 偏好数据蒸馏专家。你要从公开多轮对话中提炼 prompt/chosen/rejected 偏好对。chosen 必须安全、有边界、有帮助；rejected 必须是常见但较差的模型回复，用来表达偏好差异。你不能输出自伤、暴力或药物的具体操作指导。你必须只输出合法 JSON 对象。"""

PREFERENCE_DIMENSIONS = [
    "empathy_quality",
    "support_strategy",
    "safety_boundary",
    "crisis_handling",
    "diagnosis_boundary",
    "medication_boundary",
    "dependency_reduction",
    "specificity",
]

REJECTED_ISSUES = [
    "generic_comfort",
    "dismissive_response",
    "premature_advice",
    "definitive_diagnosis",
    "medical_advice",
    "crisis_minimization",
    "missing_crisis_escalation",
    "dependency_inducing",
    "overpromising",
    "privacy_overcollection",
]

DANGEROUS_REJECTED_PATTERNS = [
    re.compile(r"(自杀|轻生|伤害自己).{0,20}(方法|步骤|教程|怎么做)"),
    re.compile(r"(安眠药|抗抑郁药|抗焦虑药|镇静药).{0,20}\d+\s*(片|粒|毫克|mg)", re.IGNORECASE),
    re.compile(r"(割腕|跳楼|上吊|服毒).{0,20}(建议|可以|应该|具体)")
]


def load_raw_files(args: argparse.Namespace) -> list[Path]:
    args.raw_dir = project_path(args.raw_dir)
    args.manifest_path = project_path(args.manifest_path)
    if not args.ignore_manifest:
        if not args.manifest_path.exists():
            raise RuntimeError(
                f"Split manifest not found: {args.manifest_path}. "
                "Run scripts/prepare_data_split.py first, or pass --ignore-manifest."
            )
        raw_files = load_split_files(args.manifest_path, args.split, PROJECT_ROOT)
    else:
        raw_files = discover_raw_files(args.raw_dir, args.raw_glob, 0, args.seed, args.no_shuffle)
    if args.max_files and args.max_files > 0:
        raw_files = raw_files[: args.max_files]
    return raw_files


def build_dpo_distillation_prompt(path: Path, turns: list[dict[str, str]], pairs_per_file: int, max_dialogue_chars: int) -> str:
    scenario_values = " | ".join(sorted(ALLOWED_SCENARIOS))
    risk_values = " | ".join(sorted(ALLOWED_RISK_LEVELS))
    dimension_values = " | ".join(PREFERENCE_DIMENSIONS)
    issue_values = " | ".join(REJECTED_ISSUES)
    dialogue = format_dialogue_for_prompt(turns, max_dialogue_chars)
    return f"""请阅读下面完整公开对话，并把它蒸馏成中文情绪支持助手的 DPO 偏好训练对。

原始文件：{path.name}
最多输出偏好对数：{pairs_per_file}

可选 scenario：{scenario_values}
可选 risk_level：{risk_values}
可选 preference_dimension：{dimension_values}
可选 rejected_issue：{issue_values}

核心要求：
1. prompt 的 user_input 必须是自包含、自然、不模板化的一段中文来访者表达。
2. chosen 必须明显优于 rejected：更共情、更具体、更安全、更有边界。
3. chosen 不能诊断、不能治疗承诺、不能给药物建议；危机场景必须优先安全升级。
4. rejected 要像真实弱模型会犯的错误，例如空泛安慰、过早建议、诊断越界、药物建议、危机漏升级、强化 AI 依赖。
5. rejected 可以体现错误边界，但禁止包含自伤/伤人方法、药物剂量、违法操作等具体危险指导。
6. 不要直接复制原始咨询师回复；chosen 和 rejected 都要重新写。
7. chosen 建议 80-500 字，rejected 建议 30-260 字，两者不要高度相似。
8. 如果该对话不适合生成偏好对，输出 usable=false 并说明 skip_reason。

输出必须是一个 JSON 对象，格式如下：
{{
  "usable": true,
  "skip_reason": "",
  "dialogue_summary": "一句话概括完整对话，不含隐私",
  "pairs": [
    {{
      "scenario": "crisis_expression",
      "risk_level": "high",
      "user_input": "自包含的当前来访者表达",
      "chosen": "安全、有边界、有帮助的更优回复",
      "rejected": "较差但不含具体危险指导的弱模型回复",
      "preference_dimension": ["safety_boundary", "crisis_handling"],
      "rejected_issue": ["missing_crisis_escalation"],
      "judge_notes": "为什么 chosen 应优于 rejected"
    }}
  ]
}}

完整对话：
{dialogue}
"""


def call_distiller(client: Any, model: str, path: Path, turns: list[dict[str, str]], args: argparse.Namespace) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": DPO_DISTILLER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_dpo_distillation_prompt(path, turns, args.pairs_per_file, args.max_dialogue_chars),
        },
    ]
    raw = create_chat_completion_with_retry(
        client=client,
        model=model,
        messages=messages,
        max_retries=args.openai_max_retries,
    )
    parsed = extract_json_object(raw)
    if not isinstance(parsed, dict):
        raise ValueError("DPO distiller response is not a JSON object")
    return parsed


def rejected_too_dangerous(text: str) -> bool:
    return any(pattern.search(text) for pattern in DANGEROUS_REJECTED_PATTERNS)


def too_similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= 0.78


def make_dpo_row(
    *,
    index: int,
    pair: dict[str, Any],
    dialogue_summary: str,
    path: Path,
    raw_hash: str,
    turns: list[dict[str, str]],
    distiller_model: str,
    keep_unsafe_chosen: bool,
) -> tuple[dict[str, Any] | None, str]:
    user_input = anonymize_text(pair.get("user_input", ""))
    chosen = anonymize_text(pair.get("chosen", ""))
    rejected = anonymize_text(pair.get("rejected", ""))
    conversation_summary = truncate_text(anonymize_text(dialogue_summary), 500)
    if not (12 <= len(user_input) <= 900):
        return None, "bad_user_input_length"
    if not (40 <= len(chosen) <= 1600):
        return None, "bad_chosen_length"
    if not (20 <= len(rejected) <= 900):
        return None, "bad_rejected_length"
    if too_similar(chosen, rejected):
        return None, "chosen_rejected_too_similar"
    if rejected_too_dangerous(rejected):
        return None, "rejected_too_dangerous"

    scenario, risk_level = normalize_scenario_and_risk(pair, user_input + " " + conversation_summary)
    chosen_rule_flags = detect_rule_flags(chosen, risk_level)
    if chosen_rule_flags and not keep_unsafe_chosen:
        return None, "unsafe_chosen:" + ",".join(chosen_rule_flags)

    row: dict[str, Any] = {
        "id": f"dpo_gpt4o_smile_{index:06d}",
        "locale": "zh-CN",
        "created_at": CREATED_AT,
        "source": "gpt4o_distilled_smile_dpo",
        "scenario": scenario,
        "risk_level": risk_level,
        "user_input": user_input,
        "conversation_summary": conversation_summary,
        "prompt": [
            {"role": "system", "content": BASE_ASSISTANT_SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ],
        "chosen": [{"role": "assistant", "content": chosen}],
        "rejected": [{"role": "assistant", "content": rejected}],
        "chosen_response": chosen,
        "rejected_response": rejected,
        "preference_dimension": coerce_list(pair.get("preference_dimension")),
        "rejected_issue": coerce_list(pair.get("rejected_issue")),
        "judge_notes": anonymize_text(pair.get("judge_notes", "")),
        "chosen_rule_flags": chosen_rule_flags,
        "source_metadata": {
            "dataset": "SMILE / SmileChat",
            "dataset_url": SMILE_SOURCE_PAGE,
            "split": "dpo",
            "raw_file": relative_to_project(path, PROJECT_ROOT),
            "raw_file_name": path.name,
            "raw_sha256": raw_hash,
            "source_turn_count": len(turns),
            "source_role_counts": role_counts(turns),
            "distiller_model": distiller_model,
            "distillation_method": "full_dialogue_read_then_rewrite_dpo_preference_pair",
            "privacy_note": "Public dialogue was anonymized and rewritten for preference training use.",
        },
    }
    return row, ""


def deduplicate_dpo(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        h = text_hash(row.get("user_input", "") + " " + row.get("chosen_response", ""))
        if h in seen:
            continue
        seen.add(h)
        unique.append(row)
    return unique


def validate_dpo(rows: list[dict[str, Any]]) -> None:
    ids: set[str] = set()
    for idx, row in enumerate(rows, 1):
        for field in ["id", "prompt", "chosen", "rejected", "scenario", "risk_level", "source_metadata"]:
            if field not in row:
                raise ValueError(f"row {idx} missing field: {field}")
        if row["id"] in ids:
            raise ValueError(f"duplicate id: {row['id']}")
        ids.add(row["id"])
        prompt = row["prompt"]
        chosen = row["chosen"]
        rejected = row["rejected"]
        if not isinstance(prompt, list) or len(prompt) != 2:
            raise ValueError(f"bad prompt in {row['id']}")
        if not isinstance(chosen, list) or len(chosen) != 1:
            raise ValueError(f"bad chosen in {row['id']}")
        if not isinstance(rejected, list) or len(rejected) != 1:
            raise ValueError(f"bad rejected in {row['id']}")


def summarize(rows: list[dict[str, Any]], processed_rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    return {
        "dataset": "gpt4o_distilled_smile_dpo",
        "version": "v1",
        "created_at": CREATED_AT,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": len(rows),
        "target_count": args.target_count,
        "split": args.split,
        "manifest_path": relative_to_project(args.manifest_path, PROJECT_ROOT),
        "output_path": relative_to_project(args.output_path, PROJECT_ROOT),
        "processed_file_count": len(processed_rows),
        "processed_status_counts": dict(Counter(row.get("status") for row in processed_rows)),
        "scenario_counts": dict(Counter(row.get("scenario") for row in rows)),
        "risk_level_counts": dict(Counter(row.get("risk_level") for row in rows)),
        "rejected_issue_counts": dict(Counter(issue for row in rows for issue in row.get("rejected_issue", []))),
        "distiller_model": args.distiller_model,
        "retry_errors": args.retry_errors,
        "continue_on_error": args.continue_on_error,
        "workers": args.workers,
        "notes": "Full-dialogue GPT-4o distillation into DPO prompt/chosen/rejected pairs. Keep separate from eval split.",
    }


def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    args.output_path = project_path(args.output_path)
    args.summary_path = project_path(args.summary_path)
    args.processed_log_path = project_path(args.processed_log_path)
    args.workers = max(1, int(args.workers))

    if args.overwrite:
        for path in [args.output_path, args.summary_path, args.processed_log_path]:
            if path.exists():
                path.unlink()

    raw_files = load_raw_files(args)
    existing_rows = read_jsonl(args.output_path)
    processed = processed_raw_files(args.processed_log_path, args.output_path, args.retry_errors)
    pending_files = [path for path in raw_files if relative_to_project(path, PROJECT_ROOT) not in processed]
    print(
        f"[dpo] raw_files={len(raw_files)} existing_pairs={len(existing_rows)} "
        f"processed_files={len(processed)} pending_files={len(pending_files)} "
        f"target={args.target_count} split={args.split} workers={args.workers}"
    )

    if args.dry_run:
        preview = [relative_to_project(path, PROJECT_ROOT) for path in raw_files[: min(10, len(raw_files))]]
        print(json.dumps({"preview_files": preview}, ensure_ascii=False, indent=2))
        return existing_rows

    if len(existing_rows) >= args.target_count:
        summary = summarize(existing_rows, read_jsonl(args.processed_log_path), args)
        write_json(args.summary_path, summary)
        print(f"[dpo] target already satisfied, output={args.output_path}")
        return existing_rows

    client = build_openai_client()
    emitted_rows = list(existing_rows)
    next_index = len(existing_rows) + 1

    def process_one(file_index: int, path: Path) -> dict[str, Any]:
        rel_raw_file = relative_to_project(path, PROJECT_ROOT)
        processed_row: dict[str, Any] = {
            "raw_file": rel_raw_file,
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            turns = load_turns(path)
            usable, skip_reason = is_minimally_usable(turns)
            if not usable:
                processed_row.update({"status": "skipped", "skip_reason": skip_reason})
                return {"file_index": file_index, "path": path, "processed_row": processed_row, "rows": []}
            raw_hash = file_sha256(path)
            parsed = call_distiller(client, args.distiller_model, path, turns, args)
            if not parsed.get("usable", True):
                processed_row.update({"status": "skipped_by_distiller", "skip_reason": normalize_text(parsed.get("skip_reason", ""))})
                return {"file_index": file_index, "path": path, "processed_row": processed_row, "rows": []}

            pairs = parsed.get("pairs") or []
            if not isinstance(pairs, list):
                raise ValueError("DPO distiller field pairs is not a list")
            dialogue_summary = normalize_text(parsed.get("dialogue_summary", ""))
            rows: list[dict[str, Any]] = []
            rejected_counts: Counter[str] = Counter()
            for pair in pairs[: args.pairs_per_file]:
                if not isinstance(pair, dict):
                    rejected_counts["non_object_pair"] += 1
                    continue
                row, reason = make_dpo_row(
                    index=0,
                    pair=pair,
                    dialogue_summary=dialogue_summary,
                    path=path,
                    raw_hash=raw_hash,
                    turns=turns,
                    distiller_model=args.distiller_model,
                    keep_unsafe_chosen=args.keep_unsafe_chosen,
                )
                if row is None:
                    rejected_counts[reason] += 1
                    continue
                rows.append(row)
            return {
                "file_index": file_index,
                "path": path,
                "processed_row": processed_row,
                "rows": rows,
                "rejected_counts": dict(rejected_counts),
                "source_turn_count": len(turns),
                "raw_sha256": raw_hash,
            }
        except Exception as exc:
            processed_row.update({"status": "error", "error": str(exc)})
            return {"file_index": file_index, "path": path, "processed_row": processed_row, "rows": [], "error": exc}

    def write_result(result: dict[str, Any]) -> None:
        nonlocal next_index, emitted_rows
        path = result["path"]
        processed_row = result["processed_row"]
        if result.get("error") is not None:
            append_jsonl(args.processed_log_path, processed_row)
            print(f"[dpo] error raw={path.name}: {processed_row.get('error')}")
            if not (args.continue_on_error or args.allow_partial):
                raise result["error"]
            return

        if processed_row.get("status") in {"skipped", "skipped_by_distiller"}:
            append_jsonl(args.processed_log_path, processed_row)
            return

        wrote = 0
        for row in result.get("rows", []):
            if len(emitted_rows) >= args.target_count:
                break
            row["id"] = f"dpo_gpt4o_smile_{next_index:06d}"
            append_jsonl(args.output_path, row)
            emitted_rows.append(row)
            next_index += 1
            wrote += 1

        processed_row.update(
            {
                "status": "ok" if wrote else "no_valid_pairs",
                "pair_count": wrote,
                "rejected_counts": result.get("rejected_counts", {}),
                "source_turn_count": result.get("source_turn_count"),
                "raw_sha256": result.get("raw_sha256"),
                "distiller_model": args.distiller_model,
            }
        )
        append_jsonl(args.processed_log_path, processed_row)
        print(f"[dpo] file={result['file_index']}/{len(raw_files)} wrote={wrote} total={len(emitted_rows)}/{args.target_count} raw={path.name}")
        if args.openai_request_sleep > 0 and args.workers == 1:
            time.sleep(args.openai_request_sleep)

    if args.workers == 1:
        for file_index, path in enumerate(raw_files, 1):
            rel_raw_file = relative_to_project(path, PROJECT_ROOT)
            if rel_raw_file in processed:
                continue
            if len(emitted_rows) >= args.target_count:
                break
            write_result(process_one(file_index, path))
    else:
        executor = ThreadPoolExecutor(max_workers=args.workers)
        futures = [
            executor.submit(process_one, file_index, path)
            for file_index, path in enumerate(raw_files, 1)
            if relative_to_project(path, PROJECT_ROOT) not in processed
        ]
        try:
            for future in as_completed(futures):
                write_result(future.result())
                if len(emitted_rows) >= args.target_count:
                    for pending in futures:
                        pending.cancel()
                    break
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    rows = deduplicate_dpo(read_jsonl(args.output_path))
    if len(rows) != len(read_jsonl(args.output_path)):
        write_jsonl(args.output_path, rows)
    if len(rows) < args.target_count and not args.allow_partial:
        raise RuntimeError(f"Only distilled {len(rows)} DPO pairs, need {args.target_count}.")
    validate_dpo(rows)
    summary = summarize(rows, read_jsonl(args.processed_log_path), args)
    write_json(args.summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return rows

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Use GPT-4o to distill full SMILE dialogues into DPO preference pairs.")
    parser.add_argument("--target-count", type=int, default=1500)
    parser.add_argument("--max-files", type=int, default=2500, help="max split files to inspect; 0 means all split files")
    parser.add_argument("--pairs-per-file", type=int, default=1)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--split", default="dpo", choices=["sft", "dpo", "eval"])
    parser.add_argument("--raw-dir", type=Path, default=PROJECT_ROOT / "data" / "raw" / "smile")
    parser.add_argument("--raw-glob", default="*.json")
    parser.add_argument("--ignore-manifest", action="store_true")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--no-shuffle", action="store_true")
    parser.add_argument("--max-dialogue-chars", type=int, default=12000)
    parser.add_argument("--distiller-model", default=os.getenv("OPENAI_DISTILL_MODEL", OPENAI_EVAL_MODEL or "gpt-4o"))
    parser.add_argument("--openai-max-retries", type=int, default=OPENAI_MAX_RETRIES)
    parser.add_argument("--openai-request-sleep", type=float, default=OPENAI_REQUEST_SLEEP)
    parser.add_argument("--workers", type=int, default=1, help="number of concurrent API requests; start with 4-8 if your API gateway allows it")
    parser.add_argument("--output-path", type=Path, default=DPO_OUTPUT_PATH)
    parser.add_argument("--summary-path", type=Path, default=DPO_SUMMARY_PATH)
    parser.add_argument("--processed-log-path", type=Path, default=DPO_PROCESSED_LOG_PATH)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-unsafe-chosen", action="store_true", help="keep chosen rows that trip heuristic safety flags; not recommended")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run(args)


if __name__ == "__main__":
    main()
