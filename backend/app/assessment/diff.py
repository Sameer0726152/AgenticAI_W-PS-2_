"""Status changes between a run and the run before it."""
import sqlite3


def run_changes(conn: sqlite3.Connection, run_id: int, prev_run_id: int | None) -> list[dict]:
    if not prev_run_id:
        return []
    rows = conn.execute(
        """SELECT s.key, s.label, p.status AS from_status, c.status AS to_status
           FROM skill_results c
           JOIN skills s ON s.id = c.skill_id
           LEFT JOIN skill_results p ON p.run_id = ? AND p.skill_id = c.skill_id
           WHERE c.run_id = ? AND (p.status IS NULL OR p.status != c.status)
           ORDER BY s.label""",
        (prev_run_id, run_id),
    ).fetchall()
    return [
        {"skill_key": r["key"], "skill_label": r["label"],
         "from_status": r["from_status"] or "not_assessed", "to_status": r["to_status"]}
        for r in rows
    ]
