import requests
import time
import os

OLLAMA_URL     = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
PRIMARY_MODEL  = os.environ.get("OLLAMA_MODEL", "deepseek-coder:6.7b")
REVIEWER_MODEL = os.environ.get("OLLAMA_MODEL", "deepseek-coder:6.7b")


def call_ollama(prompt, model=None, retries=2, timeout=180, num_predict=512, num_ctx=2048):
    """
    num_predict=512  — enough for full kv output including reasoning + all 5 score lines.
                       At 3 tok/s CPU = 171s < 180s timeout.
                       Previously 280 caused Pass 2 to cut off before all score fields.
    timeout=180      — safe ceiling per attempt (was 120).
    retries=2        — 2 * 180s = 360s max wait.
    num_ctx=2048     — all prompts are under 500 input tokens.
    """
    if model is None:
        model = PRIMARY_MODEL

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature":    0,
            "top_p":          1,
            "repeat_penalty": 1.0,
            "seed":           42,
            "num_predict":    num_predict,
            "num_ctx":        num_ctx,
        }
    }

    for attempt in range(retries):
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
            response.raise_for_status()
            result = response.json().get("response", "").strip()
            if not result:
                raise ValueError("Empty response")
            return result
        except Exception as e:
            print(f"    [Ollama] Attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(3)

    print("    [Ollama] All retries exhausted.")
    return ""


def call_json(prompt, model=None):
    return call_ollama(prompt, model=model)


def call_reviewer(prompt):
    return call_ollama(prompt, model=REVIEWER_MODEL)