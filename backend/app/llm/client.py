"""One function for structured (JSON) LLM calls. LLM_PROVIDER picks Groq or local Ollama."""
import json
import logging
import time

import httpx

from app import config
from app.llm import cache
from app.llm.rate_limit import limiter

log = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_ATTEMPTS = 4


class LLMError(Exception):
    pass


def _estimate_tokens(messages: list[dict], max_tokens: int) -> int:
    chars = sum(len(m["content"]) for m in messages)
    return chars // 4 + max_tokens


def _request(model: str, messages: list[dict], schema: dict, schema_name: str, max_tokens: int) -> tuple[str, dict]:
    if config.LLM_PROVIDER == "groq":
        if not config.GROQ_API_KEY:
            raise LLMError("GROQ_API_KEY is not set in .env")
        url, headers = GROQ_URL, {"Authorization": f"Bearer {config.GROQ_API_KEY}"}
        body = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_completion_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
        }
        if model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
    elif config.LLM_PROVIDER == "ollama":
        url, headers = f"{config.OLLAMA_BASE_URL}/chat/completions", {}
        hint = {"role": "system", "content": "Reply with JSON only, matching this JSON schema:\n" + json.dumps(schema)}
        body = {
            "model": config.OLLAMA_MODEL,
            "messages": [hint, *messages],
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
    else:
        raise LLMError(f"Unknown LLM_PROVIDER '{config.LLM_PROVIDER}'")

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = httpx.post(url, headers=headers, json=body, timeout=120, verify=config.SSL_CONTEXT)
        except httpx.HTTPError as e:
            if attempt == MAX_ATTEMPTS:
                raise LLMError(f"LLM request failed: {e}") from e
            time.sleep(2 * attempt)
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == MAX_ATTEMPTS:
                raise LLMError(f"LLM unavailable (HTTP {resp.status_code}): {resp.text[:300]}")
            wait = float(resp.headers.get("retry-after", 5 * attempt))
            log.warning("LLM HTTP %s, retrying in %.1fs", resp.status_code, wait)
            time.sleep(min(wait, 60))
            continue
        if resp.status_code != 200:
            raise LLMError(f"LLM error (HTTP {resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise LLMError("LLM output was cut off (max tokens too low)")
        return choice["message"]["content"], data.get("usage", {})
    raise LLMError("LLM request failed")


def chat_json(
    messages: list[dict],
    schema: dict,
    schema_name: str,
    prompt_version: str,
    cache_parts: tuple,
    fast: bool = False,
    max_tokens: int = 3000,
) -> dict:
    """Call the LLM and return parsed JSON. Cached on (prompt_version, model, cache_parts)."""
    model = config.OLLAMA_MODEL if config.LLM_PROVIDER == "ollama" else (config.LLM_MODEL_FAST if fast else config.LLM_MODEL)
    key = cache.make_key(prompt_version, config.LLM_PROVIDER, model, *cache_parts)
    if (hit := cache.get(key)) is not None:
        return hit

    reservation = limiter.acquire(_estimate_tokens(messages, max_tokens))
    content, usage = _request(model, messages, schema, schema_name, max_tokens)
    tokens = usage.get("total_tokens") or _estimate_tokens(messages, 0)
    limiter.record(reservation, tokens)

    try:
        result = json.loads(content)
    except json.JSONDecodeError as e:
        raise LLMError(f"LLM returned invalid JSON: {content[:300]}") from e
    cache.put(key, model, prompt_version, result, tokens)
    return result
