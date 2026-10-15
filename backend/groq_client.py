"""
DataSentinel — Groq Cloud Client
Centralised Groq LPU inference client used by all AI engines.
Only schema metadata and computed statistics are ever transmitted — raw row data never leaves the machine.
"""

import os
import json
import requests
from dotenv import load_dotenv
from utils import logger

load_dotenv()

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Model roster — tuned for each engine's needs with environment override support
MODEL_FAST = os.getenv("GROQ_MODEL_FAST", "qwen/qwen3.8-27b")  # Fast operations & JSON parsing
MODEL_REASONING = os.getenv("GROQ_MODEL_REASONING", "openai/gpt-oss-120b")  # Deep SQL & analytical reasoning

FALLBACK_MODELS = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]


def groq_chat(
    messages: list[dict],
    model: str = MODEL_FAST,
    temperature: float = 0.2,
    json_mode: bool = False,
    max_tokens: int = 2048,
    timeout: int = 15,
) -> str | None:
    """
    Send a chat completion request to Groq LPU Cloud.

    Returns the assistant's response text, or None on failure.
    All errors are logged but never raised — callers should handle None gracefully.
    Includes automatic retry with exponential backoff for HTTP 429 rate-limit errors
    and automated model fallback on HTTP 404 model-not-found errors.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set. AI features are disabled.")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Format messages safely for json_mode if required by Groq API
    call_messages = list(messages)
    if json_mode:
        has_json_kw = any("json" in str(m.get("content", "")).lower() for m in call_messages)
        if not has_json_kw and call_messages:
            last_msg = dict(call_messages[-1])
            last_msg["content"] = str(last_msg.get("content", "")) + "\n(Please respond in valid JSON format.)"
            call_messages[-1] = last_msg

    # Prepare candidate models starting with the requested model, followed by fallbacks
    models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]

    for current_model in models_to_try:
        payload: dict = {
            "model": current_model,
            "messages": call_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        max_retries = 2
        model_failed = False

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    _GROQ_URL, headers=headers, json=payload, timeout=timeout
                )

                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        content = choices[0]["message"]["content"]
                        return content.strip()
                    return None
                elif response.status_code == 429 and attempt < max_retries:
                    # Rate limited — backoff and retry
                    import time
                    wait = 2 ** (attempt + 1)  # 2s, 4s
                    logger.warning("Groq API 429 rate-limited. Retrying in %ds (attempt %d/%d)...", wait, attempt + 1, max_retries)
                    time.sleep(wait)
                    continue
                elif response.status_code == 404:
                    logger.warning("Groq model '%s' not found (404). Trying fallback candidate...", current_model)
                    model_failed = True
                    break
                else:
                    logger.error("Groq API %d with model %s: %s", response.status_code, current_model, response.text[:300])
                    # If JSON validation or model request error, try next candidate
                    if response.status_code in (400, 422):
                        model_failed = True
                        break
                    return None

            except requests.exceptions.Timeout:
                logger.warning("Groq API request timed out after %ds for model %s.", timeout, current_model)
                return None
            except requests.exceptions.ConnectionError:
                logger.warning("Groq API connection failed. Check network connectivity.")
                return None
            except Exception as e:
                logger.error("Groq client unexpected error: %s", e)
                return None

        if not model_failed:
            return None

    return None


def groq_chat_json(
    messages: list[dict],
    model: str = MODEL_FAST,
    temperature: float = 0.1,
    timeout: int = 15,
) -> dict | list | None:
    """
    Convenience wrapper that requests JSON mode and parses the response.
    Returns parsed JSON (dict or list), or None on failure.
    """
    raw = groq_chat(
        messages,
        model=model,
        temperature=temperature,
        json_mode=True,
        timeout=timeout,
    )
    if raw is None:
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Groq JSON parse error: %s | Raw: %s", e, raw[:300])
        return None


def check_groq_connectivity() -> bool:
    """Quick connectivity check — sends a minimal request to verify API key + network."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return False
    for candidate in [MODEL_FAST, MODEL_REASONING, "qwen/qwen3.8-27b"]:
        try:
            resp = requests.post(
                _GROQ_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": candidate,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
                timeout=5,
            )
            if resp.status_code == 200:
                return True
        except Exception:
            continue
    return False
