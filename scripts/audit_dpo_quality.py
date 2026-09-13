from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.distill_dpo_with_gpt4o import rejected_too_dangerous, validate_dpo  # noqa: E402


DEFAULT_INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "dpo_train.jsonl"
DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "data" / "processed" / "dpo_quality_auto_summary.json"
DEFAULT_SAMPLE_PATH = PROJECT_ROOT / "data" / "processed" / "dpo_quality_sample.jsonl"
DEFAULT_REVIEW_PATH = PROJECT_ROOT / "docs" / "dpo_quality_review.md"


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


def response_text(row: dict[str, Any], key: str) -> str:
    direct = row.get(f"{key}_response")
    if isinstance(direct, str):
        return direct
    messages = row.get(key) or []
    if messages and isinstance(messages[0], dict):
        return str(messages[0].get("content", ""))
    return ""


def row_issue_flags(row: dict[str, Any], similarity_threshold: float) -> list[str]:
    chosen = response_text(row, "chosen")
    rejected = response_text(row, "rejected")
    flags: list[str] = []
    if row.get("chosen_rule_flags"):
        flags.append("chosen_rule_flags")
    if rejected_too_dangerous(rejected):
        flags.append("dangerous_rejected")
    if SequenceMatcher(None, chosen, rejected).ratio() >= similarity_threshold:
        flags.append("chosen_rejected_too_similar")
    if not row.get("preference_dimension"):
        flags.append("missing_preference_dimension")
    if not row.get("rejected_issue"):
        flags.append("missing_rejected_issue")
    if len(rejected) > len(chosen) * 1.2:
        flags.append("rejected_much_longer_than_chosen")
    return flags


def validate_rows(rows: list[dict[str, Any]], similarity_threshold: float) -> dict[str, Any]:
    issue_counts: Counter[str] = Counter()
    issue_examples: dict[str, list[str]] = defaultdict(list)

    try:
        validate_dpo(rows)
    except Exception as exc:
        issue_counts["validate_dpo_failed"] += 1
        issue_examples["validate_dpo_failed"].append(str(exc))

    ids = Counter(str(row.get("id", "<missing_id>")) for row in rows)
    for row_id, count in ids.items():
        if count > 1:
            issue_counts["duplicate_id"] += count
            issue_examples["duplicate_id"].append(row_id)

    raw_files = Counter(str((row.get("source_metadata") or {}).get("raw_file", "")) for row in rows)
    for raw_file, count in raw_files.items():
        if raw_file and count > 1:
            issue_counts["duplicate_raw_file"] += count
            issue_examples["duplicate_raw_file"].append(raw_file)

    for row in rows:
        row_id = str(row.get("id", "<missing_id>"))
        for flag in row_issue_flags(row, similarity_threshold):
            issue_counts[flag] += 1
            issue_examples[flag].append(row_id)

    return {
        "issue_counts": dict(issue_counts),
        "issue_examples": {key: value[:20] for key, value in issue_examples.items()},
    }


def stratified_sample(rows: list[dict[str, Any]], sample_size: int, seed: int, similarity_threshold: float) -> list[dict[str, Any]]:
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

    def add_one(candidates: list[dict[str, Any]]) -> None:
        rng.shuffle(candidates)
        for candidate in candidates:
            row_id = str(candidate.get("id"))
            if row_id not in selected_ids:
                selected.append(candidate)
                selected_ids.add(row_id)
                return

    issue_rows = [row for row in rows if row_issue_flags(row, similarity_threshold)]
    for row in issue_rows:
        if len(selected) >= sample_size:
            break
        add_one([row])

    for row in rows:
        scenario = str(row.get("scenario", "unknown"))
        risk = str(row.get("risk_level", "unknown"))
        buckets[(scenario, risk)].append(row)
        scenarios[scenario].append(row)
        risks[risk].append(row)

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
    user_lengths = [len(str(row.get("user_input", ""))) for row in rows]
    chosen_lengths = [len(response_text(row, "chosen")) for row in rows]
    rejected_lengths = [len(response_text(row, "rejected")) for row in rows]
    preference_dimensions = Counter(dim for row in rows for dim in row.get("preference_dimension", []) if isinstance(dim, str))
    rejected_issues = Counter(issue for row in rows for issue in row.get("rejected_issue", []) if isinstance(issue, str))
    validation = validate_rows(rows, args.similarity_threshold)

    return {
        "input_path": str(args.input_path.relative_to(PROJECT_ROOT) if args.input_path.is_relative_to(PROJECT_ROOT) else args.input_path),
        "total": len(rows),
        "sample_size": len(sampled_rows),
        "seed": args.seed,
        "similarity_threshold": args.similarity_threshold,
        "scenario_counts": dict(Counter(str(row.get("scenario", "unknown")) for row in rows)),
        "risk_level_counts": dict(Counter(str(row.get("risk_level", "unknown")) for row in rows)),
        "sample_scenario_counts": dict(Counter(str(row.get("scenario", "unknown")) for row in sampled_rows)),
        "sample_risk_level_counts": dict(Counter(str(row.get("risk_level", "unknown")) for row in sampled_rows)),
        "preference_dimension_counts": dict(preference_dimensions),
        "rejected_issue_counts": dict(rejected_issues),
        "user_input_length": length_stats(user_lengths),
        "chosen_response_length": length_stats(chosen_lengths),
        "rejected_response_length": length_stats(rejected_lengths),
        **validation,
    }


def render_review_markdown(sampled_rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines: list[str] = [
        "# DPO Quality Review",
        "",
        "## Scope",
        "",
        f"- Total DPO pairs: {summary['total']}",
        f"- Review sample size: {summary['sample_size']}",
        f"- Seed: {summary['seed']}",
        "",
        "## Rubric",
        "",
        "For each pair, mark one decision and score the four dimensions from 1 to 5.",
        "",
        "- Decision: pass / rewrite / drop",
        "- Chosen safety: no diagnosis, medication instruction, crisis mishandling, or AI dependency",
        "- Chosen quality: empathy, specificity, boundary setting, and useful next step",
        "- Preference contrast: chosen is clearly better than rejected",
        "- Rejected usefulness: rejected shows a realistic weakness without dangerous operational details",
        "",
        "Hard fail if chosen is unsafe, rejected includes concrete self-harm or medication instructions, or chosen/rejected are too similar.",
        "",
        "## Auto Summary",
        "",
        "```json",
        json.dumps(
            {
                "scenario_counts": summary["scenario_counts"],
                "risk_level_counts": summary["risk_level_counts"],
                "issue_counts": summary["issue_counts"],
                "preference_dimension_counts": summary["preference_dimension_counts"],
                "rejected_issue_counts": summary["rejected_issue_counts"],
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
        pref = ", ".join(row.get("preference_dimension") or [])
        issues = ", ".join(row.get("rejected_issue") or [])
        chosen_flags = ", ".join(row.get("chosen_rule_flags") or [])
        lines.extend(
            [
                f"### {idx:03d}. {row.get('id', '<missing_id>')}",
                "",
                f"- Scenario: `{row.get('scenario', 'unknown')}`",
                f"- Risk: `{row.get('risk_level', 'unknown')}`",
                f"- Preference dimension: `{pref or 'none'}`",
                f"- Rejected issue: `{issues or 'none'}`",
                f"- Chosen rule flags: `{chosen_flags or 'none'}`",
                "",
                "**User**",
                "",
                str(row.get("user_input", "")).strip(),
                "",
                "**Chosen**",
                "",
                response_text(row, "chosen").strip(),
                "",
                "**Rejected**",
                "",
                response_text(row, "rejected").strip(),
                "",
                "**Judge Notes**",
                "",
                str(row.get("judge_notes", "")).strip(),
                "",
                "**Manual Review**",
                "",
                "- Decision: [ ] pass  [ ] rewrite  [ ] drop",
                "- Chosen safety: /5",
                "- Chosen quality: /5",
                "- Preference contrast: /5",
                "- Rejected usefulness: /5",
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
    sampled_rows = stratified_sample(rows, args.sample_size, args.seed, args.similarity_threshold)
    summary = build_summary(rows, sampled_rows, args)

    write_json(args.summary_path, summary)
    write_jsonl(args.sample_path, sampled_rows)
    args.review_path.parent.mkdir(parents=True, exist_ok=True)
    args.review_path.write_text(render_review_markdown(sampled_rows, summary), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a DPO quality audit package with stratified manual review samples.")
    parser.add_argument("--input-path", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--sample-path", type=Path, default=DEFAULT_SAMPLE_PATH)
    parser.add_argument("--review-path", type=Path, default=DEFAULT_REVIEW_PATH)
    parser.add_argument("--sample-size", type=int, default=150, help="manual review sample size; 150 is 10 percent of 1500")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--similarity-threshold", type=float, default=0.78)
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
