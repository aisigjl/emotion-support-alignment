from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RAW_SMILE_DIR = PROJECT_ROOT / "data" / "raw" / "smile"
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "data" / "processed" / "smile_split_manifest.json"
CREATED_AT = "2026-09-09"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_path(path: Path, project_root: Path = PROJECT_ROOT) -> Path:
    return path if path.is_absolute() else project_root / path


def relative_to_project(path: Path, project_root: Path = PROJECT_ROOT) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def parse_file_id(path: Path) -> int | None:
    try:
        return int(path.stem)
    except ValueError:
        return None


def file_sort_key(path: Path) -> tuple[int, str]:
    file_id = parse_file_id(path)
    if file_id is None:
        return (10**12, path.name)
    return (file_id, path.name)


def discover_raw_files(raw_dir: Path, raw_glob: str, max_files: int) -> list[Path]:
    files = [path for path in raw_dir.glob(raw_glob) if path.is_file()]
    files.sort(key=file_sort_key)
    if max_files and max_files > 0:
        files = files[:max_files]
    return files


def split_counts(total: int, sft_ratio: float, dpo_ratio: float, eval_ratio: float) -> dict[str, int]:
    ratio_sum = sft_ratio + dpo_ratio + eval_ratio
    if total <= 0:
        return {"sft": 0, "dpo": 0, "eval": 0}
    if abs(ratio_sum - 1.0) > 1e-6:
        raise ValueError(f"split ratios must sum to 1.0, got {ratio_sum}")
    sft_count = int(total * sft_ratio)
    dpo_count = int(total * dpo_ratio)
    eval_count = total - sft_count - dpo_count
    return {"sft": sft_count, "dpo": dpo_count, "eval": eval_count}


def make_file_record(path: Path, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    return {
        "raw_file": relative_to_project(path, project_root),
        "raw_file_name": path.name,
        "file_id": parse_file_id(path),
    }


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    raw_dir = project_path(args.raw_dir)
    files = discover_raw_files(raw_dir, args.raw_glob, args.max_files)
    if not files:
        raise RuntimeError(f"No raw files matched {raw_dir}/{args.raw_glob}")

    rng = random.Random(args.seed)
    shuffled = list(files)
    rng.shuffle(shuffled)

    counts = split_counts(len(shuffled), args.sft_ratio, args.dpo_ratio, args.eval_ratio)
    sft_end = counts["sft"]
    dpo_end = sft_end + counts["dpo"]
    split_files = {
        "sft": shuffled[:sft_end],
        "dpo": shuffled[sft_end:dpo_end],
        "eval": shuffled[dpo_end:],
    }

    return {
        "dataset": "SMILE / SmileChat",
        "version": "v1_file_level_split",
        "created_at": CREATED_AT,
        "built_at": utc_now(),
        "raw_dir": relative_to_project(raw_dir),
        "raw_glob": args.raw_glob,
        "seed": args.seed,
        "max_files": args.max_files,
        "total_files": len(files),
        "split_ratios": {
            "sft": args.sft_ratio,
            "dpo": args.dpo_ratio,
            "eval": args.eval_ratio,
        },
        "split_counts": {split: len(paths) for split, paths in split_files.items()},
        "splits": {
            split: [make_file_record(path) for path in paths]
            for split, paths in split_files.items()
        },
        "leakage_rule": "A raw_file must belong to exactly one split. Do not use eval split files for SFT or DPO.",
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_split_files(manifest_path: Path, split: str, project_root: Path = PROJECT_ROOT) -> list[Path]:
    manifest_path = project_path(manifest_path, project_root)
    manifest = load_manifest(manifest_path)
    splits = manifest.get("splits")
    if not isinstance(splits, dict):
        raise ValueError(f"Bad manifest: missing splits in {manifest_path}")
    rows = splits.get(split)
    if not isinstance(rows, list):
        raise ValueError(f"Bad manifest: missing split {split!r} in {manifest_path}")

    paths: list[Path] = []
    for row in rows:
        if isinstance(row, dict):
            raw_file = row.get("raw_file")
        else:
            raw_file = row
        if not raw_file:
            continue
        path = Path(str(raw_file))
        if not path.is_absolute():
            path = project_root / path
        paths.append(path)
    return paths


def print_summary(manifest: dict[str, Any], output_path: Path | None = None) -> None:
    summary = {
        "dataset": manifest.get("dataset"),
        "total_files": manifest.get("total_files"),
        "split_counts": manifest.get("split_counts"),
        "seed": manifest.get("seed"),
    }
    if output_path is not None:
        summary["output_path"] = relative_to_project(output_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a file-level SMILE split manifest for SFT/DPO/Eval.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_SMILE_DIR)
    parser.add_argument("--raw-glob", default="*.json")
    parser.add_argument("--output-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--sft-ratio", type=float, default=0.70)
    parser.add_argument("--dpo-ratio", type=float, default=0.15)
    parser.add_argument("--eval-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-files", type=int, default=0, help="0 means all matched files")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.output_path = project_path(args.output_path)
    if args.output_path.exists() and not args.overwrite and not args.dry_run:
        print(f"[split] manifest already exists: {args.output_path}")
        print_summary(load_manifest(args.output_path), args.output_path)
        return

    manifest = build_manifest(args)
    if args.dry_run:
        print_summary(manifest)
        return

    write_json(args.output_path, manifest)
    print_summary(manifest, args.output_path)


if __name__ == "__main__":
    main()
