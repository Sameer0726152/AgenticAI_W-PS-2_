import json

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app import db
from app.assessment.diff import run_changes
from app.assessment.pipeline import execute_run, handle_new_commit, start_run
from app.github.client import GitHubError
from app.schemas import Run, RunSummary

router = APIRouter(prefix="/api", tags=["assessments"])

STATUS_ORDER = {"demonstrated": 0, "partially_demonstrated": 1, "not_demonstrated": 2}

RUN_SELECT = """SELECT r.*, s.commit_sha, s.commit_message FROM runs r
                JOIN snapshots s ON s.id = r.snapshot_id"""


def _summary(conn, row) -> dict:
    return {
        **{k: row[k] for k in ("id", "repo_id", "commit_sha", "commit_message", "trigger", "status", "error",
                               "prev_run_id", "started_at", "finished_at")},
        "changed_files": json.loads(row["changed_files"]),
        "affected_skills": json.loads(row["affected_skills"]),
        "changes": run_changes(conn, row["id"], row["prev_run_id"]) if row["status"] == "done" else [],
    }


def load_run(conn, run_id: int) -> Run:
    row = conn.execute(f"{RUN_SELECT} WHERE r.id = ?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Run not found")
    results = conn.execute(
        """SELECT sr.*, sk.key AS skill_key, sk.label AS skill_label FROM skill_results sr
           JOIN skills sk ON sk.id = sr.skill_id WHERE sr.run_id = ?""",
        (run_id,),
    ).fetchall()
    skills = []
    for r in results:
        evidence = conn.execute("SELECT * FROM evidence WHERE skill_result_id = ? ORDER BY id", (r["id"],)).fetchall()
        skills.append({
            "skill_key": r["skill_key"], "skill_label": r["skill_label"], "status": r["status"],
            "confidence": r["confidence"], "rationale": r["rationale"], "method": r["method"],
            "carried_over": r["carried_from_run_id"] is not None,
            "evidence": [
                {k: e[k] for k in ("path", "start_line", "end_line", "snippet", "permalink", "source")}
                | {"verified": bool(e["verified"])}
                for e in evidence
            ],
        })
    skills.sort(key=lambda s: (STATUS_ORDER[s["status"]], s["skill_label"]))
    return Run(**_summary(conn, row), skills=skills)


@router.post("/repos/{repo_id}/assess", status_code=202)
def assess_repo(repo_id: int, background: BackgroundTasks):
    with db.transaction() as conn:
        if not conn.execute("SELECT 1 FROM repos WHERE id = ?", (repo_id,)).fetchone():
            raise HTTPException(404, "Repository not found")
        if conn.execute("SELECT 1 FROM runs WHERE repo_id = ? AND status = 'running'", (repo_id,)).fetchone():
            raise HTTPException(409, "An assessment is already running for this repository")
        run_id = start_run(conn, repo_id, "manual")
    background.add_task(execute_run, run_id)
    return {"run_id": run_id, "status": "running"}


@router.post("/repos/{repo_id}/check")
def check_now(repo_id: int, background: BackgroundTasks):
    """'Check now' button: same path as the poller, triggered immediately."""
    try:
        result = handle_new_commit(repo_id, "manual")
    except ValueError as e:
        raise HTTPException(404, str(e))
    except GitHubError as e:
        raise HTTPException(e.status_code, str(e))
    if result["new_commit"] and result["run_id"]:
        background.add_task(execute_run, result["run_id"])
    return result


@router.get("/runs/{run_id}", response_model=Run)
def get_run(run_id: int):
    with db.transaction() as conn:
        return load_run(conn, run_id)


@router.get("/runs/{run_id}/diff")
def get_diff(run_id: int):
    with db.transaction() as conn:
        row = conn.execute("SELECT id, prev_run_id FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Run not found")
        return {"run_id": run_id, "prev_run_id": row["prev_run_id"],
                "changes": run_changes(conn, run_id, row["prev_run_id"])}


@router.get("/repos/{repo_id}/runs", response_model=list[RunSummary])
def list_runs(repo_id: int, limit: int = 20):
    with db.transaction() as conn:
        rows = conn.execute(f"{RUN_SELECT} WHERE r.repo_id = ? ORDER BY r.id DESC LIMIT ?", (repo_id, limit)).fetchall()
        return [_summary(conn, r) for r in rows]


@router.get("/gaps")
def get_gaps(repo_id: int, job_id: int):
    from app.assessment.gaps import gap_analysis  # avoids a circular import (gaps uses load_run)

    with db.transaction() as conn:
        result = gap_analysis(conn, repo_id, job_id)
    if result is None:
        raise HTTPException(404, "Job not found")
    return result


@router.get("/repos/{repo_id}/latest-run")
def latest_run(repo_id: int):
    with db.transaction() as conn:
        repo = conn.execute("SELECT last_polled_at, polling_enabled FROM repos WHERE id = ?", (repo_id,)).fetchone()
        row = conn.execute(
            "SELECT id, status FROM runs WHERE repo_id = ? ORDER BY id DESC LIMIT 1", (repo_id,)
        ).fetchone()
    return {
        "run_id": row["id"] if row else None,
        "status": row["status"] if row else None,
        "last_polled_at": repo["last_polled_at"] if repo else None,
        "polling": bool(repo["polling_enabled"]) if repo else False,
    }
