"""Skill list: starter skills from database/seed/skills.json, plus skills the LLM adds."""
import json
import re
import sqlite3

from app import config

SEED_PATH = config.ROOT_DIR / "database" / "seed" / "skills.json"


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9+#]+", " ", text.lower()).strip()


def seed_skills(conn: sqlite3.Connection) -> None:
    """Insert starter skills; re-running picks up edits to skills.json."""
    for s in json.loads(SEED_PATH.read_text(encoding="utf-8")):
        conn.execute(
            """INSERT INTO skills (key, label, category, synonyms, rule_hints, created_by)
               VALUES (?, ?, ?, ?, ?, 'seed')
               ON CONFLICT(key) DO UPDATE SET
                 label = excluded.label, category = excluded.category,
                 synonyms = excluded.synonyms, rule_hints = excluded.rule_hints
               WHERE skills.created_by = 'seed'""",
            (
                s["key"], s["label"], s["category"], json.dumps(s["synonyms"]),
                json.dumps(s["rule_hints"]) if s.get("rule_hints") else None,
            ),
        )


def list_skills(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM skills ORDER BY created_by DESC, id").fetchall()


def find_skill(conn: sqlite3.Connection, text: str) -> sqlite3.Row | None:
    """Match a key, label or synonym (case/punctuation-insensitive)."""
    wanted = normalize(text)
    if not wanted:
        return None
    for row in list_skills(conn):
        names = [row["key"], row["label"], *json.loads(row["synonyms"])]
        if wanted in (normalize(n) for n in names):
            return row
    return None


def resolve_skill(conn: sqlite3.Connection, skill_key: str, new_label: str) -> sqlite3.Row:
    """Return the skill for an LLM-chosen key, falling back to synonym match, then creating it."""
    row = conn.execute("SELECT * FROM skills WHERE key = ?", (skill_key,)).fetchone()
    if row:
        return row
    label = (new_label or skill_key).strip()
    row = find_skill(conn, label)
    if row:
        return row

    base = normalize(label).replace(" ", "_")[:40] or "skill"
    key, n = base, 2
    while conn.execute("SELECT 1 FROM skills WHERE key = ?", (key,)).fetchone():
        key, n = f"{base}_{n}", n + 1
    conn.execute(
        "INSERT INTO skills (key, label, category, synonyms, rule_hints, created_by) "
        "VALUES (?, ?, 'other', '[]', NULL, 'llm')",
        (key, label),
    )
    return conn.execute("SELECT * FROM skills WHERE key = ?", (key,)).fetchone()
