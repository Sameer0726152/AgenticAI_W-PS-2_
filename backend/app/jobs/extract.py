"""LLM extracts skill requirements from posting text; every quote is checked against the text."""
import json
import re
import sqlite3

from app.llm.client import chat_json
from app.skills.taxonomy import list_skills, resolve_skill

PROMPT_VERSION = "jobs-v1"
MAX_TEXT_CHARS = 14000

SYSTEM_PROMPT = """You extract technical skill requirements from a job posting.

Rules:
- Include only technical skills that could be shown in a code repository: languages, frameworks,
  databases, tools, and engineering practices (testing, CI/CD, version control, API design...).
- Exclude degrees, years of experience, location, work authorization, benefits and soft skills.
- "quote" must be copied EXACTLY, character for character, from the posting: the shortest full
  sentence or bullet point that states the requirement. Never paraphrase or merge bullets.
- importance = "preferred" if the posting marks it as nice-to-have, preferred, bonus or "a plus";
  otherwise "required".
- skill_key: use a key from the provided skill list when it fits (synonyms count). Otherwise use
  "new" and put a short skill name in new_skill_label. When skill_key is not "new", new_skill_label is "".
- One entry per skill. If one sentence names several skills, emit one entry per skill with the same quote.
- title and company: as stated in the posting, or "" if not stated."""

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "company": {"type": "string"},
        "requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "skill_key": {"type": "string"},
                    "new_skill_label": {"type": "string"},
                    "importance": {"type": "string", "enum": ["required", "preferred"]},
                    "quote": {"type": "string"},
                },
                "required": ["skill_key", "new_skill_label", "importance", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "company", "requirements"],
    "additionalProperties": False,
}

_QUOTE_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def _norm(text: str) -> str:
    text = text.translate(_QUOTE_CHARS).lower()
    text = re.sub(r"^\s*[-*•]\s*", "", text)  # leading bullet marker
    return re.sub(r"\s+", " ", text).strip().rstrip(".;:")


def quote_in_text(quote: str, text: str) -> bool:
    q = _norm(quote)
    return len(q) >= 8 and q in _norm(text)


def extract_requirements(conn: sqlite3.Connection, text: str) -> dict:
    """Returns {title, company, requirements: [...], dropped: int}."""
    skills = list_skills(conn)
    skill_lines = "\n".join(
        f"- {s['key']}: {s['label']} (synonyms: {', '.join(json.loads(s['synonyms'])) or 'none'})" for s in skills
    )
    posting = text[:MAX_TEXT_CHARS]
    result = chat_json(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Skill list:\n{skill_lines}\n\nJob posting:\n\"\"\"\n{posting}\n\"\"\""},
        ],
        schema=SCHEMA,
        schema_name="job_requirements",
        prompt_version=PROMPT_VERSION,
        cache_parts=(posting, skill_lines),
    )

    requirements: dict[int, dict] = {}
    dropped = 0
    for item in result["requirements"]:
        if not quote_in_text(item["quote"], text):
            dropped += 1
            continue
        skill = resolve_skill(conn, item["skill_key"], item["new_skill_label"])
        existing = requirements.get(skill["id"])
        # Keep one entry per skill; "required" wins over "preferred".
        if existing and not (existing["importance"] == "preferred" and item["importance"] == "required"):
            continue
        requirements[skill["id"]] = {
            "skill_id": skill["id"],
            "importance": item["importance"],
            "quote": item["quote"].strip(),
        }
    return {
        "title": result["title"].strip(),
        "company": result["company"].strip(),
        "requirements": list(requirements.values()),
        "dropped": dropped,
    }
