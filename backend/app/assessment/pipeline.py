"""The core assessment pipeline. Every trigger (connect, manual, poll, webhook) ends up here."""
import json
import logging
import sqlite3

from app import db
from app.analysis import rules
from app.github import client

log = logging.getLogger(__name__)


def skills_of_interest(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every skill that at least one saved job requires or prefers."""
    return conn.execute(
        "SELECT DISTINCT s.* FROM skills s JOIN job_requirements r ON r.skill_id = s.id ORDER BY s.id"
    ).fetchall()


def snapshot_texts(conn: sqlite3.Connection, snapshot_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT f.path, b.content FROM snapshot_files f JOIN blobs b ON b.blob_sha = f.blob_sha
           WHERE f.snapshot_id = ? AND f.included = 1 AND b.content IS NOT NULL ORDER BY f.path""",
        (snapshot_id,),
    ).fetchall()
    return [{"path": r["path"], "content": r["content"]} for r in rows]


def start_run(conn: sqlite3.Connection, repo_id: int, trigger: str) -> int:
    snap = conn.execute("SELECT id FROM snapshots WHERE repo_id = ? ORDER BY id DESC LIMIT 1", (repo_id,)).fetchone()
    if not snap:
        raise ValueError("Repository has no snapshot yet")
    prev = conn.execute(
        "SELECT id FROM runs WHERE repo_id = ? AND status = 'done' ORDER BY id DESC LIMIT 1", (repo_id,)
    ).fetchone()
    cur = conn.execute(
        "INSERT INTO runs (repo_id, snapshot_id, prev_run_id, trigger, status, started_at) VALUES (?, ?, ?, ?, 'running', ?)",
        (repo_id, snap["id"], prev["id"] if prev else None, trigger, db.utc_now()),
    )
    return cur.lastrowid


def _save_result(conn, run_id: int, skill_id: int, result: rules.RuleResult, repo, commit_sha: str) -> None:
    cur = conn.execute(
        "INSERT INTO skill_results (run_id, skill_id, status, confidence, rationale, method) VALUES (?, ?, ?, ?, ?, 'rules')",
        (run_id, skill_id, result.status, result.confidence, result.rationale),
    )
    owner, name = repo["owner"], repo["name"]
    for ev in result.evidence:
        if ev.kind == "history":
            link = f"https://github.com/{owner}/{name}/commits/{commit_sha}"
        else:
            link = client.permalink(owner, name, commit_sha, ev.path, ev.start_line, ev.end_line)
        conn.execute(
            """INSERT INTO evidence (skill_result_id, path, start_line, end_line, snippet, commit_sha, permalink, source, verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'rule', 1)""",
            (cur.lastrowid, ev.path, ev.start_line, ev.end_line, ev.snippet, commit_sha, link),
        )


def execute_run(run_id: int) -> None:
    """Assess every skill of interest on the run's snapshot. Safe to call from a background task."""
    try:
        with db.transaction() as conn:
            run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            repo = conn.execute("SELECT * FROM repos WHERE id = ?", (run["repo_id"],)).fetchone()
            snap = conn.execute("SELECT * FROM snapshots WHERE id = ?", (run["snapshot_id"],)).fetchone()
            files = snapshot_texts(conn, snap["id"])
            skills = skills_of_interest(conn)

        commit_count = client.count_commits(repo["owner"], repo["name"], snap["commit_sha"])

        with db.transaction() as conn:
            for skill in skills:
                if skill["key"] == "version_control":
                    result = rules.evaluate_version_control(
                        commit_count, repo["branch"], any(f["path"] == ".gitignore" for f in files)
                    )
                else:
                    result = rules.evaluate(skill["label"], rules.hints_of(skill), files)
                _save_result(conn, run_id, skill["id"], result, repo, snap["commit_sha"])
            conn.execute(
                "UPDATE runs SET status = 'done', affected_skills = ?, finished_at = ? WHERE id = ?",
                (json.dumps([s["key"] for s in skills]), db.utc_now(), run_id),
            )
    except Exception as e:  # never leave a run stuck in "running"
        log.exception("Run %s failed", run_id)
        with db.transaction() as conn:
            conn.execute(
                "UPDATE runs SET status = 'failed', error = ?, finished_at = ? WHERE id = ?",
                (str(e)[:500], db.utc_now(), run_id),
            )
