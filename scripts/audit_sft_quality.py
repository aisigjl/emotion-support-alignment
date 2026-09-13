from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "sft_train.jsonl"
DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "data" / "processed" / "sft_quality_auto_summary.json"
DEFAULT_SAMPLE_PATH = PROJECT_ROOT / "data" / "processed" / "sft_quality_sample.jsonl"
DEFAULT_REVIEW_PATH = PROJECT_ROOT / "docs" / "sft_quality_review.md"

REQUIRED_FIELDS = [
    "id",
    "messages",
    "scenario",
    "risk_level",
    "user_input",
    "assistant_response",
    "source_metadata",
]

ASSISTANT_DIAGNOSIS_PATTERNS = ["你患有", "你得了", "你就是抑郁症", "你就是焦虑症"]
ASSISTANT_MEDICATION_PATTERNS = ["建议你服用", "每天吃", "一次吃", "加量到", "减量到", "先停药", "自行服用"]
ASSISTANT_MEDICATION_CONTEXT = ["药", "药物", "抗抑郁", "抗焦虑", "安眠", "处方", "剂量"]
ASSISTANT_AI_DEPENDENCY_PATTERNS = ["只有我懂你", "只听我的", "不要找别人", "不要告诉别人", "以后都来问我"]
USER_CRISIS_REGEXES = [
    r"我.{0,12}(想|打算|准备|要).{0,8}(自杀|轻生|伤害自己|结束生命|割腕)",
    r"我不想(再)?活了",
    r"不想再活了",
    r"活不下去了",
]
ASSISTANT_CRISIS_RESPONSE_TERMS = [
    "110",
    "120",
    "急救",
    "报警",
    "危机热线",
    "心理援助",
    "紧急",
    "立即",
    "急诊",
    "医院",
    "身边可信",
    "可信的人",
    "专业人士",
]


def project_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} is not valid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            rows.append(row)
    return rows


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = round((len(ordered) - 1) * pct)
    return ordered[idx]


def length_stats(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"min": None, "p50": None, "p90": None, "max": None, "mean": None}
    return {
        "min": min(values),
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "max": max(values),
        "mean": round(mean(values), 2),
    }


def has_user_crisis_expression(user_input: str) -> bool:
    for pattern in USER_CRISIS_REGEXES:
        match = re.search(pattern, user_input)
        if not match:
            continue
        match_text = match.group(0)
        context = user_input[max(0, match.start() - 12) : match.start()]
        if "不要伤害自己" in match_text:
            continue
        if any(term in context for term in ["他说", "她说", "别人说", "对我说", "说过", "听到"]):
            continue
        return True
    return False


def find_pattern_flags(row: dict[str, Any]) -> list[str]:
    user_input = str(row.get("user_input", ""))
    assistant_response = str(row.get("assistant_response", ""))
    flags: list[str] = []

    if any(pattern in assistant_response for pattern in ASSISTANT_DIAGNOSIS_PATTERNS):
        flags.append("possible_diagnosis")
    if "诊断为" in assistant_response and not any(term in assistant_response for term in ["被诊断为", "医生诊断为", "专业诊断为"]):
        flags.append("possible_diagnosis")

    has_medication_context = any(term in assistant_response for term in ASSISTANT_MEDICATION_CONTEXT)
    if has_medication_context and any(pattern in assistant_response for pattern in ASSISTANT_MEDICATION_PATTERNS):
        flags.append("possible_medication_advice")

    if any(pattern in assistant_response for pattern in ASSISTANT_AI_DEPENDENCY_PATTERNS):
        flags.append("possible_ai_dependency")

    assistant_has_crisis_response = any(term in assistant_response for term in ASSISTANT_CRISIS_RESPONSE_TERMS)
    if has_user_crisis_expression(user_input) and not assistant_has_crisis_response:
        flags.append("possible_crisis_gap")
    return flags


def validate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ids: Counter[str] = Counter()
    user_inputs: Counter[str] = Counter()
    issues: Counter[str] = Counter()
    issue_examples: dict[str, list[str]] = defaultdict(list)

    for row in rows:
        row_id = str(row.get("id", "<missing_id>"))
        ids[row_id] += 1
        user_inputs[str(row.get("user_input", ""))] += 1

        for field in REQUIRED_FIELDS:
            if field not in row:
                issues[f"missing_{field}"] += 1
                issue_examples[f"missing_{field}"].append(row_id)

        messages = row.get("messages")
        if not isinstance(messages, list) or [m.get("role") for m in messages if isinstance(m, dict)] != ["system", "user", "assistant"]:
            issues["bad_messages"] += 1
            issue_examples["bad_messages"].append(row_id)

        if len(str(row.get("user_input", ""))) < 12:
            issues["short_user_input"] += 1
            issue_examples["short_user_input"].append(row_id)
        if len(str(row.get("assistant_response", ""))) < 40:
            issues["short_assistant_response"] += 1
            issue_examples["short_assistant_response"].append(row_id)

        rule_flags = row.get("rule_flags") or []
        if rule_flags:
            issues["non_empty_rule_flags"] += 1
            issue_examples["non_empty_rule_flags"].append(row_id)

        for flag in find_pattern_flags(row):
            issues[flag] += 1
            issue_examples[flag].append(row_id)

    duplicated_ids = sorted(row_id for row_id, count in ids.items() if count > 1)
    duplicated_user_inputs = sum(1 for _, count in user_inputs.items() if count > 1)
    if duplicated_ids:
        issues["duplicate_id"] = len(duplicated_ids)
        issue_examples["duplicate_id"] = duplicated_ids[:20]
    if duplicated_user_inputs:
        issues["duplicate_user_input"] = duplicated_user_inputs

    return {
        "issue_counts": dict(issues),
        "issue_examples": {key: value[:20] for key, value in issue_examples.items()},
    }


def stratified_sample(rows: list[dict[str, Any]], sample_size: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    if sample_size <= 0 or sample_size >= len(rows):
        sampled = list(rows)
        rng.shuffle(sampled)
        return sampled

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    scenarios: dict[str, list[dict[str, Any]]] = defaultdict(list)
    risks: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        scenario = str(row.get("scenario", "unknown"))
        risk = str(row.get("risk_level", "unknown"))
        buckets[(scenario, risk)].append(row)
        scenarios[scenario].append(row)
        risks[risk].append(row)

    def add_one(candidates: list[dict[str, Any]]) -> None:
        rng.shuffle(candidates)
        for candidate in candidates:
            row_id = str(candidate.get("id"))
            if row_id not in selected_ids:
                selected.append(candidate)
                selected_ids.add(row_id)
                return

    for candidates in scenarios.values():
        add_one(list(candidates))
    for candidates in risks.values():
        add_one(list(candidates))
    for candidates in buckets.values():
        if len(selected) >= sample_size:
            break
        add_one(list(candidates))

    remaining = [row for row in rows if str(row.get("id")) not in selected_ids]
    rng.shuffle(remaining)
    selected.extend(remaining[: max(0, sample_size - len(selected))])
    rng.shuffle(selected)
    return selected[:sample_size]


def build_summary(rows: list[dict[str, Any]], sampled_rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    validation = validate_rows(rows)
    user_lengths = [len(str(row.get("user_input", ""))) for row in rows]
    assistant_lengths = [len(str(row.get("assistant_response", ""))) for row in rows]
    quality_tags = Counter(tag for row in rows for tag in row.get("quality_tags", []) if isinstance(tag, str))

    return {
        "input_path": str(args.input_path.relative_to(PROJECT_ROOT) if args.input_path.is_relative_to(PROJECT_ROOT) else args.input_path),
        "total": len(rows),
        "sample_size": len(sampled_rows),
        "seed": args.seed,
        "scenario_counts": dict(Counter(str(row.get("scenario", "unknown")) for row in rows)),
        "risk_level_counts": dict(Counter(str(row.get("risk_level", "unknown")) for row in rows)),
        "sample_scenario_counts": dict(Counter(str(row.get("scenario", "unknown")) for row in sampled_rows)),
        "sample_risk_level_counts": dict(Counter(str(row.get("risk_level", "unknown")) for row in sampled_rows)),
        "quality_tag_counts": dict(quality_tags),
        "user_input_length": length_stats(user_lengths),
        "assistant_response_length": length_stats(assistant_lengths),
        **validation,
    }


def render_review_markdown(sampled_rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines: list[str] = [
        "# SFT Quality Review",
        "",
        "## Scope",
        "",
        f"- Total SFT rows: {summary['total']}",
        f"- Review sample size: {summary['sample_size']}",
        f"- Seed: {summary['seed']}",
        "",
        "## Rubric",
        "",
        "For each item, mark one decision and score the four dimensions from 1 to 5.",
        "",
        "- Decision: pass / rewrite / drop",
        "- Safety: no diagnosis, no medication instruction, no crisis mishandling, no AI dependency",
        "- Empathy: validates emotion without exaggerating or flattering",
        "- Helpfulness: gives a concrete but low-risk next step or open question",
        "- Naturalness: Chinese expression is fluent, non-template-like, and concise enough",
        "",
        "Hard fail if the assistant gives diagnosis, treatment plan, medication dosage, crisis minimization, or encourages relying only on AI.",
        "",
        "## Auto Summary",
        "",
        "```json",
        json.dumps(
            {
                "scenario_counts": summary["scenario_counts"],
                "risk_level_counts": summary["risk_level_counts"],
                "issue_counts": summary["issue_counts"],
                "user_input_length": summary["user_input_length"],
                "assistant_response_length": summary["assistant_response_length"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
        "## Review Items",
        "",
    ]

    for idx, row in enumerate(sampled_rows, 1):
        tags = ", ".join(row.get("quality_tags") or [])
        rule_flags = ", ".join(row.get("rule_flags") or [])
        lines.extend(
            [
                f"### {idx:03d}. {row.get('id', '<missing_id>')}",
                "",
                f"- Scenario: `{row.get('scenario', 'unknown')}`",
                f"- Risk: `{row.get('risk_level', 'unknown')}`",
                f"- Quality tags: `{tags or 'none'}`",
                f"- Rule flags: `{rule_flags or 'none'}`",
                "",
                "**User**",
                "",
                str(row.get("user_input", "")).strip(),
                "",
                "**Assistant**",
                "",
                str(row.get("assistant_response", "")).strip(),
                "",
                "**Manual Review**",
                "",
                "- Decision: [ ] pass  [ ] rewrite  [ ] drop",
                "- Safety: /5",
                "- Empathy: /5",
                "- Helpfulness: /5",
                "- Naturalness: /5",
                "- Notes:",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def run(args: argparse.Namespace) -> None:
    args.input_path = project_path(args.input_path)
    args.summary_path = project_path(args.summary_path)
    args.sample_path = project_path(args.sample_path)
    args.review_path = project_path(args.review_path)

    rows = read_jsonl(args.input_path)
    sampled_rows = stratified_sample(rows, args.sample_size, args.seed)
    summary = build_summary(rows, sampled_rows, args)

    write_json(args.summary_path, summary)
    write_jsonl(args.sample_path, sampled_rows)
    args.review_path.parent.mkdir(parents=True, exist_ok=True)
    args.review_path.write_text(render_review_markdown(sampled_rows, summary), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an SFT quality audit package with stratified manual review samples.")
    parser.add_argument("--input-path", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--sample-path", type=Path, default=DEFAULT_SAMPLE_PATH)
    parser.add_argument("--review-path", type=Path, default=DEFAULT_REVIEW_PATH)
    parser.add_argument("--sample-size", type=int, default=250, help="manual review sample size; 250 is 5 percent of 5000")
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
