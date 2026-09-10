from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BASELINE_DATA_PATH = Path(
    os.getenv("BASELINE_DATA_PATH", ROOT / "data" / "eval" / "base_eval.jsonl")
)
BASE_MODEL_PATH = os.getenv(
    "BASE_MODEL_PATH", "/home/WangChanghui/wch/model/Qwen3-4B-Instruct-2507"
)
BASE_MODEL_NAME = os.getenv("BASE_MODEL_NAME", "Qwen3_4b_instruct_2507_base")

SEED = int(os.getenv("SEED", "42"))
NUM_SAMPLES = int(os.getenv("NUM_SAMPLES", "400"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "4"))
MAX_INPUT_TOKENS = int(os.getenv("MAX_INPUT_TOKENS", "2048"))
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "512"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
TOP_P = float(os.getenv("TOP_P", "0.9"))

OUTPUT_DIR = Path(os.getenv("BASELINE_OUTPUT_DIR", ROOT / "outputs" / "baseline"))
BASELINE_RESPONSES_PATH = Path(
    os.getenv("BASELINE_RESPONSES_PATH", OUTPUT_DIR / f"{BASE_MODEL_NAME}_responses.jsonl")
)
BASELINE_JUDGE_PATH = Path(
    os.getenv("BASELINE_JUDGE_PATH", OUTPUT_DIR / f"{BASE_MODEL_NAME}_judge.jsonl")
)
BASELINE_SUMMARY_PATH = Path(
    os.getenv("BASELINE_SUMMARY_PATH", OUTPUT_DIR / f"{BASE_MODEL_NAME}_eval_summary.json")
)
BASELINE_REPORT_PATH = Path(
    os.getenv(
        "BASELINE_REPORT_PATH",
        ROOT / "outputs" / "eval_reports" / f"{BASE_MODEL_NAME}_baseline_eval_report.md",
    )
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None
OPENAI_EVAL_MODEL = os.getenv("OPENAI_EVAL_MODEL", "gpt-4o")
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
OPENAI_REQUEST_SLEEP = float(os.getenv("OPENAI_REQUEST_SLEEP", "0.0"))
