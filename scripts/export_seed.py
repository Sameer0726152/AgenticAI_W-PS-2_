"""Export the local demo data (jobs, requirements, LLM cache, tracked repos) to database/seed/demo_data.json.

The deployed server starts with an empty database (free hosting has no persistent disk) and imports this file,
so the demo works without spending LLM tokens. Run from the project root:  python scripts/export_seed.py
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "career_coach.db"
OUT = ROOT / "database" / "seed" / "demo_data.json"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row


def rows(sql):
    return [dict(r) for r in conn.execute(sql)]


data = {
    "skills": rows("SELECT key, label, category, synonyms, rule_hints FROM skills WHERE created_by = 'llm'"),
    "jobs": rows("SELECT id, source_type, source_url, company, title, location, raw_text, fetched_at FROM jobs"),
    "requirements": rows(
        """SELECT r.job_id, s.key AS skill_key, r.importance, r.source_quote, r.quote_verified
           FROM job_requirements r JOIN skills s ON s.id = r.skill_id"""
    ),
    "llm_cache": rows("SELECT cache_key, model, prompt_version, response, tokens_used, created_at FROM llm_cache"),
    "repos": rows("SELECT owner, name, branch FROM repos"),
}
OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
print(f"Wrote {OUT.relative_to(ROOT)}: " + ", ".join(f"{len(v)} {k}" for k, v in data.items()))
