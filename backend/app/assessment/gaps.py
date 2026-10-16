"""Gap analysis: a job's requirements next to the repo's latest skill results."""
import sqlite3

from app.assessment.routes import load_run

STATUS_RANK = {"not_demonstrated": 0, "not_assessed": 1, "partially_demonstrated": 2, "demonstrated": 3}


def _message(status: str, label: str) -> str:
    if status == "demonstrated":
        return f"{label} is demonstrated in this repository."
    if status == "partially_demonstrated":
        return f"Some evidence of {label}, but limited. More substantial use would strengthen it."
    if status == "not_assessed":
        return "Not assessed yet. Re-run the assessment to include this skill."
    return (f"No evidence of {label} was found in the analyzed files of this repository. "
            "This does not mean the skill is absent; it is simply not shown here.")


def gap_analysis(conn: sqlite3.Connection, repo_id: int, job_id: int) -> dict | None:
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        return None
    run_row = conn.execute(
        "SELECT id FROM runs WHERE repo_id = ? AND status = 'done' ORDER BY id DESC LIMIT 1", (repo_id,)
    ).fetchone()
    run = load_run(conn, run_row["id"]) if run_row else None
    results = {s.skill_key: s for s in run.skills} if run else {}

    reqs = conn.execute(
        """SELECT r.importance, r.source_quote, s.key, s.label FROM job_requirements r
           JOIN skills s ON s.id = r.skill_id WHERE r.job_id = ?""",
        (job_id,),
    ).fetchall()

    rows = []
    for r in reqs:
        res = results.get(r["key"])
        status = res.status if res else "not_assessed"
        rows.append({
            "skill_key": r["key"],
            "skill_label": r["label"],
            "importance": r["importance"],
            "quote": r["source_quote"],
            "status": status,
            "confidence": res.confidence if res else None,
            "rationale": res.rationale if res else None,
            "message": _message(status, r["label"]),
            "evidence": [e.model_dump() for e in res.evidence] if res else [],
        })
    # Required first, then gaps before strengths.
    rows.sort(key=lambda x: (x["importance"] != "required", STATUS_RANK[x["status"]], x["skill_label"]))

    def count(importance, statuses):
        return sum(1 for x in rows if x["importance"] == importance and x["status"] in statuses)

    return {
        "job": {"id": job["id"], "company": job["company"], "title": job["title"], "source_url": job["source_url"]},
        "run_id": run.id if run else None,
        "commit_sha": run.commit_sha if run else None,
        "commit_message": run.commit_message if run else None,
        "assessed_at": run.finished_at if run else None,
        "rows": rows,
        "summary": {
            "required_total": count("required", STATUS_RANK),
            "required_demonstrated": count("required", {"demonstrated"}),
            "required_partial": count("required", {"partially_demonstrated"}),
            "preferred_total": count("preferred", STATUS_RANK),
            "preferred_demonstrated": count("preferred", {"demonstrated"}),
            "preferred_partial": count("preferred", {"partially_demonstrated"}),
        },
    }
