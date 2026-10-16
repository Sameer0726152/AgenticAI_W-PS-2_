"""A snapshot = one commit of a repo: its file list plus the contents of the files we analyze."""
import sqlite3

from app import db
from app.analysis.file_filter import select_files
from app.github import client
from app.github.client import Head


def ensure_blobs(conn: sqlite3.Connection, owner: str, name: str, blob_shas: list[str]) -> None:
    """Download contents for blobs not seen before (unchanged files are never re-fetched)."""
    for sha in blob_shas:
        if conn.execute("SELECT 1 FROM blobs WHERE blob_sha = ?", (sha,)).fetchone():
            continue
        text = client.get_blob_text(owner, name, sha)
        conn.execute(
            "INSERT OR IGNORE INTO blobs (blob_sha, content, is_binary) VALUES (?, ?, ?)",
            (sha, text, int(text is None)),
        )


def take_snapshot(conn: sqlite3.Connection, repo: sqlite3.Row, head: Head) -> int:
    """Store the commit, its selected files and their contents. Returns the snapshot id (reuses existing)."""
    existing = conn.execute(
        "SELECT id FROM snapshots WHERE repo_id = ? AND commit_sha = ?", (repo["id"], head.sha)
    ).fetchone()
    if existing:
        return existing["id"]

    files = select_files(client.get_tree(repo["owner"], repo["name"], head.sha))
    cur = conn.execute(
        "INSERT INTO snapshots (repo_id, commit_sha, commit_message, committed_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (repo["id"], head.sha, head.message, head.committed_at, db.utc_now()),
    )
    snapshot_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO snapshot_files (snapshot_id, path, blob_sha, size, included, skip_reason) VALUES (?, ?, ?, ?, ?, ?)",
        [(snapshot_id, f["path"], f["sha"], f["size"], int(f["included"]), f["skip_reason"]) for f in files],
    )
    ensure_blobs(conn, repo["owner"], repo["name"], [f["sha"] for f in files if f["included"]])
    conn.execute(
        "UPDATE repos SET last_seen_sha = ?, etag = ?, last_polled_at = ? WHERE id = ?",
        (head.sha, head.etag, db.utc_now(), repo["id"]),
    )
    return snapshot_id


def latest_snapshot(conn: sqlite3.Connection, repo_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM snapshots WHERE repo_id = ? ORDER BY id DESC LIMIT 1", (repo_id,)
    ).fetchone()


def snapshot_files(conn: sqlite3.Connection, snapshot_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM snapshot_files WHERE snapshot_id = ? ORDER BY included DESC, path", (snapshot_id,)
    ).fetchall()
