"""Fill an empty database from database/seed/demo_data.json (used by the deployed server, whose disk is wiped
on every restart). Imports jobs, requirements and the LLM cache, then reconnects the demo repo; the initial
assessment hits the cache, so it costs no tokens."""
import json
import logging
import threading

from app import config, db
from app.assessment.pipeline import execute_run, start_run
from app.github import client
from app.github.snapshot import take_snapshot

log = logging.getLogger(__name__)
SEED_FILE = config.ROOT_DIR / "database" / "seed" / "demo_data.json"


def import_seed() -> list[dict]:
    """Returns the repos to connect (empty if the database already had data or there is no seed file)."""
    if not SEED_FILE.exists():
        return []
    with db.transaction() as conn:
        if conn.execute("SELECT 1 FROM jobs LIMIT 1").fetchone():
            return []
        data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
        for s in data["skills"]:
            conn.execute(
                "INSERT OR IGNORE INTO skills (key, label, category, synonyms, rule_hints, created_by) "
                "VALUES (?, ?, ?, ?, ?, 'llm')",
                (s["key"], s["label"], s["category"], s["synonyms"], s["rule_hints"]),
            )
        skill_ids = {r["key"]: r["id"] for r in conn.execute("SELECT id, key FROM skills")}
        job_ids = {}
        for j in data["jobs"]:
            cur = conn.execute(
                "INSERT INTO jobs (source_type, source_url, company, title, location, raw_text, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (j["source_type"], j["source_url"], j["company"], j["title"], j["location"], j["raw_text"],
                 j["fetched_at"]),
            )
            job_ids[j["id"]] = cur.lastrowid
        conn.executemany(
            "INSERT OR IGNORE INTO job_requirements (job_id, skill_id, importance, source_quote, quote_verified) "
            "VALUES (?, ?, ?, ?, ?)",
            [(job_ids[r["job_id"]], skill_ids[r["skill_key"]], r["importance"], r["source_quote"],
              r["quote_verified"]) for r in data["requirements"] if r["skill_key"] in skill_ids],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO llm_cache (cache_key, model, prompt_version, response, tokens_used, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(c["cache_key"], c["model"], c["prompt_version"], c["response"], c["tokens_used"], c["created_at"])
             for c in data["llm_cache"]],
        )
        has_repos = conn.execute("SELECT 1 FROM repos LIMIT 1").fetchone()
    log.info("Imported seed: %d jobs, %d cached LLM answers", len(data["jobs"]), len(data["llm_cache"]))
    return [] if has_repos else data["repos"]


def connect_repos(repos: list[dict]) -> None:
    for r in repos:
        try:
            head = client.get_head(r["owner"], r["name"], r["branch"])
            with db.transaction() as conn:
                cur = conn.execute(
                    "INSERT INTO repos (owner, name, branch, created_at) VALUES (?, ?, ?, ?)",
                    (r["owner"], r["name"], r["branch"], db.utc_now()),
                )
                repo = conn.execute("SELECT * FROM repos WHERE id = ?", (cur.lastrowid,)).fetchone()
                take_snapshot(conn, repo, head)
                run_id = start_run(conn, repo["id"], "initial")
            execute_run(run_id)
            log.info("Seed repo %s/%s connected and assessed", r["owner"], r["name"])
        except Exception:
            log.exception("Could not connect seed repo %s/%s", r["owner"], r["name"])


def run() -> None:
    repos = import_seed()
    if repos:
        threading.Thread(target=connect_repos, args=(repos,), name="seed-repos", daemon=True).start()
