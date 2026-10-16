"""Stores LLM answers so identical inputs never cost tokens twice."""
import hashlib
import json

from app import db


def make_key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def get(key: str) -> dict | None:
    with db.transaction() as conn:
        row = conn.execute("SELECT response FROM llm_cache WHERE cache_key = ?", (key,)).fetchone()
    return json.loads(row["response"]) if row else None


def put(key: str, model: str, prompt_version: str, response: dict, tokens_used: int) -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?, ?, ?, ?)",
            (key, model, prompt_version, json.dumps(response), tokens_used, db.utc_now()),
        )
