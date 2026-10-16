from fastapi import APIRouter, HTTPException, Response

from app import db
from app.github import client
from app.github.client import GitHubError
from app.github.snapshot import latest_snapshot, snapshot_files, take_snapshot
from app.schemas import Repo, RepoCreate

router = APIRouter(prefix="/api/repos", tags=["repos"])


def _load_repo(conn, repo_id: int) -> Repo:
    repo = conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,)).fetchone()
    if not repo:
        raise HTTPException(404, "Repository not found")
    owner, name = repo["owner"], repo["name"]
    snap = latest_snapshot(conn, repo_id)
    snapshot = None
    if snap:
        files = snapshot_files(conn, snap["id"])
        snapshot = {
            "id": snap["id"],
            "commit_sha": snap["commit_sha"],
            "commit_message": snap["commit_message"],
            "committed_at": snap["committed_at"],
            "commit_url": f"https://github.com/{owner}/{name}/commit/{snap['commit_sha']}",
            "files_included": sum(f["included"] for f in files),
            "files_skipped": sum(not f["included"] for f in files),
            "files": [
                {
                    "path": f["path"], "size": f["size"], "included": bool(f["included"]),
                    "skip_reason": f["skip_reason"],
                    "url": client.permalink(owner, name, snap["commit_sha"], f["path"]),
                }
                for f in files
            ],
        }
    return Repo(
        id=repo["id"],
        full_name=f"{owner}/{name}",
        branch=repo["branch"],
        html_url=f"https://github.com/{owner}/{name}",
        polling=bool(repo["polling_enabled"]),
        last_polled_at=repo["last_polled_at"],
        latest_snapshot=snapshot,
    )


@router.post("", response_model=Repo, status_code=201)
def connect_repo(payload: RepoCreate, response: Response):
    try:
        owner, name = client.parse_full_name(payload.full_name)
        branch = (payload.branch or "").strip() or client.get_default_branch(owner, name)
        with db.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM repos WHERE owner = ? AND name = ? AND branch = ?", (owner, name, branch)
            ).fetchone()
            if existing:
                response.status_code = 200
                return _load_repo(conn, existing["id"])

        head = client.get_head(owner, name, branch)
        with db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO repos (owner, name, branch, created_at) VALUES (?, ?, ?, ?)",
                (owner, name, branch, db.utc_now()),
            )
            repo = conn.execute("SELECT * FROM repos WHERE id = ?", (cur.lastrowid,)).fetchone()
            take_snapshot(conn, repo, head)
            return _load_repo(conn, repo["id"])
    except GitHubError as e:
        raise HTTPException(e.status_code, str(e))


@router.get("", response_model=list[Repo])
def list_repos():
    with db.transaction() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM repos ORDER BY id")]
        return [_load_repo(conn, i) for i in ids]


@router.get("/{repo_id}", response_model=Repo)
def get_repo(repo_id: int):
    with db.transaction() as conn:
        return _load_repo(conn, repo_id)


@router.delete("/{repo_id}", status_code=204)
def delete_repo(repo_id: int):
    with db.transaction() as conn:
        conn.execute("DELETE FROM repos WHERE id = ?", (repo_id,))
