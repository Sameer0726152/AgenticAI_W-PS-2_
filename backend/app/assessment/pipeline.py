"""The core assessment pipeline. Every trigger (connect, manual, poll, webhook) ends up here."""
import json
import logging
import sqlite3
import threading
from dataclasses import dataclass

from app import db
from app.analysis import llm_evidence, rules
from app.assessment.affected import affected_skills
from app.github import client
from app.github.client import GitHubError
from app.github.snapshot import take_snapshot
from app.llm.client import LLMError
from app.llm.rate_limit import BudgetExceeded

log = logging.getLogger(__name__)

MAX_EVIDENCE = 5
_repo_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


@dataclass
class FinalResult:
    status: str
    confidence: str | None
    rationale: str
    method: str  # rules | llm | rules+llm
    evidence: list[rules.Evidence]


def _repo_lock(repo_id: int) -> threading.Lock:
    with _locks_guard:
        return _repo_locks.setdefault(repo_id, threading.Lock())


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


def assess_skill(skill: sqlite3.Row, files: list[dict], rule: rules.RuleResult) -> FinalResult:
    """Combine rule evidence with an LLM review. Nothing is 'demonstrated' without verified evidence."""
    hints = rules.hints_of(skill)
    if skill["key"] == "version_control" or not llm_evidence.has_signal(skill, hints, files, rule):
        return FinalResult(rule.status, rule.confidence, rule.rationale, "rules", rule.evidence)

    try:
        llm = llm_evidence.assess(skill, hints, files, rule)
    except (LLMError, BudgetExceeded) as e:
        log.warning("LLM review failed for %s: %s", skill["key"], e)
        return FinalResult(rule.status, rule.confidence, f"{rule.rationale} (LLM review unavailable: rules only)",
                           "rules", rule.evidence)

    dropped = f" ({llm.dropped} unverifiable citation(s) discarded.)" if llm.dropped else ""
    if llm.status != "not_demonstrated" and llm.evidence:
        llm_spans = {(e.path, e.start_line) for e in llm.evidence}
        extra = [e for e in rule.evidence if (e.path, e.start_line) not in llm_spans]
        return FinalResult(llm.status, llm.confidence, llm.rationale + dropped,
                           "rules+llm" if rule.evidence else "llm", (llm.evidence + extra)[:MAX_EVIDENCE])
    if rule.status != "not_demonstrated":
        # The LLM cannot take away what the rules proved; it found no further verified evidence.
        return FinalResult(rule.status, rule.confidence, rule.rationale + dropped, "rules", rule.evidence)
    return FinalResult("not_demonstrated", None, llm.rationale + dropped, "rules+llm", [])


def start_run(conn: sqlite3.Connection, repo_id: int, trigger: str, changed_files: list[dict] | None = None) -> int:
    """Create a run for the repo's latest snapshot. changed_files given = incremental (affected skills only)."""
    snap = conn.execute("SELECT id FROM snapshots WHERE repo_id = ? ORDER BY id DESC LIMIT 1", (repo_id,)).fetchone()
    if not snap:
        raise ValueError("Repository has no snapshot yet")
    prev = conn.execute(
        "SELECT id FROM runs WHERE repo_id = ? AND status = 'done' ORDER BY id DESC LIMIT 1", (repo_id,)
    ).fetchone()
    cur = conn.execute(
        """INSERT INTO runs (repo_id, snapshot_id, prev_run_id, trigger, changed_files, status, started_at)
           VALUES (?, ?, ?, ?, ?, 'running', ?)""",
        (repo_id, snap["id"], prev["id"] if prev else None, trigger, json.dumps(changed_files or []), db.utc_now()),
    )
    return cur.lastrowid


def start_runs_for_new_skills() -> list[int]:
    """After a job is added: re-assess repos whose latest run lacks some skill of interest.
    Already-assessed skills come from the LLM cache, so only the new skills cost tokens."""
    run_ids = []
    with db.transaction() as conn:
        wanted = {s["id"] for s in skills_of_interest(conn)}
        for repo in conn.execute("SELECT id FROM repos").fetchall():
            if conn.execute("SELECT 1 FROM runs WHERE repo_id = ? AND status = 'running'", (repo["id"],)).fetchone():
                continue
            last = conn.execute(
                "SELECT id FROM runs WHERE repo_id = ? AND status = 'done' ORDER BY id DESC LIMIT 1", (repo["id"],)
            ).fetchone()
            have = {r["skill_id"] for r in conn.execute("SELECT skill_id FROM skill_results WHERE run_id = ?", (last["id"],))} if last else set()
            if last and wanted - have:
                run_ids.append(start_run(conn, repo["id"], "new_skills"))
    return run_ids


def handle_new_commit(repo_id: int, trigger: str) -> dict:
    """Poller, "Check now" button and webhook all call this. Detects a new commit on the tracked branch,
    snapshots it and creates an incremental run. Returns {new_commit, commit_sha, run_id}.
    The caller executes the run (execute_run) wherever suits it."""
    with _repo_lock(repo_id):
        with db.transaction() as conn:
            repo = conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,)).fetchone()
            busy = conn.execute("SELECT 1 FROM runs WHERE repo_id = ? AND status = 'running'", (repo_id,)).fetchone()
        if not repo:
            raise ValueError("Repository not found")

        head = client.get_head(repo["owner"], repo["name"], repo["branch"], etag=repo["etag"])
        with db.transaction() as conn:
            conn.execute("UPDATE repos SET last_polled_at = ? WHERE id = ?", (db.utc_now(), repo_id))
            if head and head.sha == repo["last_seen_sha"]:
                conn.execute("UPDATE repos SET etag = ? WHERE id = ?", (head.etag, repo_id))
        if head is None or head.sha == repo["last_seen_sha"]:
            return {"new_commit": False, "commit_sha": repo["last_seen_sha"], "run_id": None}
        if busy:  # don't snapshot yet; the next check will pick the commit up
            return {"new_commit": True, "commit_sha": head.sha, "run_id": None, "deferred": True}

        changed = None
        if repo["last_seen_sha"]:
            try:
                changed = client.compare(repo["owner"], repo["name"], repo["last_seen_sha"], head.sha)
            except GitHubError as e:
                log.warning("Compare failed (%s); doing a full assessment", e)

        with db.transaction() as conn:
            snapshot_id = take_snapshot(conn, repo, head)
            done = conn.execute("SELECT id FROM runs WHERE snapshot_id = ? AND status = 'done'", (snapshot_id,)).fetchone()
            if done:  # this commit was already assessed (e.g. by another trigger)
                return {"new_commit": False, "commit_sha": head.sha, "run_id": done["id"]}
            run_id = start_run(conn, repo_id, trigger, changed)
        log.info("New commit %s on repo %s (%s): run %s", head.sha[:7], repo_id, trigger, run_id)
        return {"new_commit": True, "commit_sha": head.sha, "run_id": run_id}


def _save_result(conn, run_id: int, skill_id: int, result: FinalResult, repo, commit_sha: str) -> None:
    cur = conn.execute(
        "INSERT INTO skill_results (run_id, skill_id, status, confidence, rationale, method) VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, skill_id, result.status, result.confidence, result.rationale, result.method),
    )
    owner, name = repo["owner"], repo["name"]
    for ev in result.evidence:
        if ev.kind == "history":
            link = f"https://github.com/{owner}/{name}/commits/{commit_sha}"
        else:
            link = client.permalink(owner, name, commit_sha, ev.path, ev.start_line, ev.end_line)
        conn.execute(
            """INSERT INTO evidence (skill_result_id, path, start_line, end_line, snippet, commit_sha, permalink, source, verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (cur.lastrowid, ev.path, ev.start_line, ev.end_line, ev.snippet, commit_sha, link, ev.source),
        )


def _carry_over(conn, run_id: int, prev: sqlite3.Row) -> None:
    """Copy an unaffected skill's previous result (and evidence) into this run."""
    cur = conn.execute(
        """INSERT INTO skill_results (run_id, skill_id, status, confidence, rationale, method, carried_from_run_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (run_id, prev["skill_id"], prev["status"], prev["confidence"], prev["rationale"], prev["method"],
         prev["carried_from_run_id"] or prev["run_id"]),
    )
    conn.execute(
        """INSERT INTO evidence (skill_result_id, path, start_line, end_line, snippet, commit_sha, permalink, source, verified)
           SELECT ?, path, start_line, end_line, snippet, commit_sha, permalink, source, verified
           FROM evidence WHERE skill_result_id = ? ORDER BY id""",
        (cur.lastrowid, prev["id"]),
    )


def execute_run(run_id: int) -> None:
    """Assess the run's snapshot: all skills of interest, or only affected ones for an incremental run."""
    try:
        with db.transaction() as conn:
            run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            repo = conn.execute("SELECT * FROM repos WHERE id = ?", (run["repo_id"],)).fetchone()
            snap = conn.execute("SELECT * FROM snapshots WHERE id = ?", (run["snapshot_id"],)).fetchone()
            files = snapshot_texts(conn, snap["id"])
            skills = skills_of_interest(conn)
            changed = json.loads(run["changed_files"])
            prev_results = {}
            prev_paths: dict[str, set[str]] = {}
            if run["prev_run_id"]:
                for r in conn.execute(
                    "SELECT sr.*, s.key FROM skill_results sr JOIN skills s ON s.id = sr.skill_id WHERE sr.run_id = ?",
                    (run["prev_run_id"],),
                ):
                    prev_results[r["key"]] = r
                    prev_paths[r["key"]] = {
                        e["path"] for e in conn.execute("SELECT path FROM evidence WHERE skill_result_id = ?", (r["id"],))
                    }

        if changed and prev_results:
            contents = {f["path"]: f["content"] for f in files}
            affected = affected_skills(skills, changed, prev_paths, contents)
        else:
            affected = {s["key"] for s in skills}

        needs_history = any(s["key"] == "version_control" for s in skills if s["key"] in affected)
        commit_count = client.count_commits(repo["owner"], repo["name"], snap["commit_sha"]) if needs_history else 0

        # LLM calls can wait on the rate limiter, so compute everything before opening a write transaction.
        results = []
        for skill in skills:
            if skill["key"] not in affected:
                continue
            if skill["key"] == "version_control":
                rule = rules.evaluate_version_control(
                    commit_count, repo["branch"], any(f["path"] == ".gitignore" for f in files)
                )
            else:
                rule = rules.evaluate(skill["label"], rules.hints_of(skill), files)
            results.append((skill, assess_skill(skill, files, rule)))

        with db.transaction() as conn:
            for skill, result in results:
                _save_result(conn, run_id, skill["id"], result, repo, snap["commit_sha"])
            for skill in skills:
                if skill["key"] not in affected:
                    _carry_over(conn, run_id, prev_results[skill["key"]])
            conn.execute(
                "UPDATE runs SET status = 'done', affected_skills = ?, finished_at = ? WHERE id = ?",
                (json.dumps(sorted(affected)), db.utc_now(), run_id),
            )
    except Exception as e:  # never leave a run stuck in "running"
        log.exception("Run %s failed", run_id)
        with db.transaction() as conn:
            conn.execute(
                "UPDATE runs SET status = 'failed', error = ?, finished_at = ? WHERE id = ?",
                (str(e)[:500], db.utc_now(), run_id),
            )
