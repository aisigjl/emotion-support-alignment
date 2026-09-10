# Environment Setup

## 1. Recommended Environment

Use Python 3.10 or 3.11.

This project is configured for a local base model at:

```text
/home/WangChanghui/wch/model/Qwen3-4B-Instruct-2507
```

The dependency file targets CUDA 12.4 by using the official PyTorch `cu124` wheel index and `torch==2.6.0`.

## 2. Install Dependencies

From the project root:

```bash
cd /home/WangChanghui/wch/llm/emotion-support-alignment
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
```

After installation, verify CUDA visibility:

```bash
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
```

Expected result:

```text
torch version starts with 2.6.0
CUDA version should be 12.4 or compatible cu124
cuda.is_available() should be True on a GPU machine
```

## 3. OpenAI API Evaluation

The evaluation judge is planned to use a strong closed model API, for example `gpt-4o`.

Create a local `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Then fill in:

```text
OPENAI_API_KEY=your_api_key_here
OPENAI_EVAL_MODEL=gpt-4o
```

`OPENAI_BASE_URL` is optional. Leave it empty when using the official OpenAI API endpoint.

The official OpenAI Python SDK provides synchronous and asynchronous clients and supports the Responses API. No separate `httpx` dependency is needed for the default client.

Do not commit `.env` to git.

## 4. Why vLLM Is Not Included Yet

`vllm` is intentionally not included in the first `requirements.txt`. It often pins specific PyTorch and CUDA combinations, which can conflict with SFT/DPO dependencies. The first project stage only needs Transformers-based local generation. Add a separate `requirements-vllm.txt` later during the inference optimization stage.

## 5. Next Step

After dependencies are installed, the next implementation task is to write a baseline generation script:

```text
scripts/run_baseline_generation.py
```

That script should read `data/eval/base_eval.jsonl`, run the local Qwen model on each `user_input`, and save outputs to `outputs/baseline/base_responses.jsonl`.
