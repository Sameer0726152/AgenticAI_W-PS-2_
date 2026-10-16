from fastapi import APIRouter, HTTPException, Response

from app import db
from app.jobs.extract import extract_requirements
from app.jobs.fetch import JobFetchError, fetch_job
from app.llm.client import LLMError
from app.llm.rate_limit import BudgetExceeded
from app.schemas import Job, JobCreate, JobSummary

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _load_job(conn, job_id: int, dropped: int = 0) -> Job:
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        raise HTTPException(404, "Job not found")
    reqs = conn.execute(
        """SELECT r.id, s.key AS skill_key, s.label AS skill_label, r.importance,
                  r.source_quote AS quote, r.quote_verified
           FROM job_requirements r JOIN skills s ON s.id = r.skill_id
           WHERE r.job_id = ?
           ORDER BY r.importance = 'preferred', r.id""",
        (job_id,),
    ).fetchall()
    return Job(
        **{k: job[k] for k in ("id", "company", "title", "location", "source_url", "source_type", "fetched_at")},
        requirements=[dict(r) for r in reqs],
        dropped_requirements=dropped,
    )


@router.post("", response_model=Job, status_code=201)
def create_job(payload: JobCreate, response: Response):
    with db.transaction() as conn:
        existing = conn.execute("SELECT id FROM jobs WHERE source_url = ?", (payload.url.strip(),)).fetchone()
        if existing:
            response.status_code = 200
            return _load_job(conn, existing["id"])

    try:
        fetched = fetch_job(payload.url, payload.text)
    except JobFetchError as e:
        raise HTTPException(e.status_code, str(e))

    with db.transaction() as conn:
        try:
            extracted = extract_requirements(conn, fetched.text)
        except BudgetExceeded as e:
            raise HTTPException(429, str(e))
        except LLMError as e:
            raise HTTPException(502, f"Requirement extraction failed: {e}")

        cur = conn.execute(
            "INSERT INTO jobs (source_type, source_url, company, title, location, raw_text, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                fetched.source_type, fetched.source_url,
                fetched.company or extracted["company"] or None,
                fetched.title or extracted["title"] or None,
                fetched.location, fetched.text, db.utc_now(),
            ),
        )
        job_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO job_requirements (job_id, skill_id, importance, source_quote, quote_verified) "
            "VALUES (?, ?, ?, ?, 1)",
            [(job_id, r["skill_id"], r["importance"], r["quote"]) for r in extracted["requirements"]],
        )
        return _load_job(conn, job_id, dropped=extracted["dropped"])


@router.get("", response_model=list[JobSummary])
def list_jobs():
    with db.transaction() as conn:
        rows = conn.execute(
            """SELECT j.id, j.company, j.title, j.source_url, COUNT(r.id) AS requirement_count
               FROM jobs j LEFT JOIN job_requirements r ON r.job_id = j.id
               GROUP BY j.id ORDER BY j.id"""
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: int):
    with db.transaction() as conn:
        return _load_job(conn, job_id)


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: int):
    with db.transaction() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
