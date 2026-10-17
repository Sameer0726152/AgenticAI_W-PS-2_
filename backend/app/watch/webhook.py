"""GitHub push webhook: same pipeline as the poller, triggered instantly. Polling stays on as a fallback."""
import hashlib
import hmac
import json
import logging
import time

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app import config, db
from app.assessment.pipeline import execute_run, handle_new_commit

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# repo_id -> ISO time of the last accepted push (shown in the UI)
last_webhook_at: dict[int, str] = {}
HEAD_RETRIES = 3  # GitHub's API can lag a moment behind the push event


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def process_push(repo_id: int, after_sha: str) -> None:
    """Background task: detect the new commit (retrying if the API is behind) and assess it."""
    for attempt in range(HEAD_RETRIES):
        result = handle_new_commit(repo_id, "webhook")
        if result.get("run_id") and result["new_commit"]:
            execute_run(result["run_id"])
            return
        if result.get("deferred") or result.get("commit_sha") == after_sha:
            return  # a run is busy (the poller picks it up later) or this commit was already handled
        time.sleep(2 * (attempt + 1))
    log.warning("Webhook for repo %s: GitHub API never showed %s; polling will catch it", repo_id, after_sha[:7])


@router.post("/github", status_code=202)
async def github_webhook(
    request: Request,
    background: BackgroundTasks,
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
):
    if not config.GITHUB_WEBHOOK_SECRET:
        raise HTTPException(503, "GITHUB_WEBHOOK_SECRET is not set in .env")
    body = await request.body()
    if not verify_signature(config.GITHUB_WEBHOOK_SECRET, body, x_hub_signature_256):
        raise HTTPException(401, "Invalid signature")

    if x_github_event == "ping":
        return JSONResponse({"ok": True, "event": "ping"}, status_code=200)
    if x_github_event != "push":
        return {"ignored": f"event '{x_github_event}'"}

    payload = json.loads(body)
    full_name = (payload.get("repository") or {}).get("full_name", "")
    ref = payload.get("ref", "")
    after = payload.get("after", "")
    with db.transaction() as conn:
        if x_github_delivery:
            cur = conn.execute(
                "INSERT OR IGNORE INTO webhook_deliveries (delivery_id, received_at) VALUES (?, ?)",
                (x_github_delivery, db.utc_now()),
            )
            if cur.rowcount == 0:
                return {"ignored": "duplicate delivery"}
        repo = conn.execute(
            "SELECT id, branch FROM repos WHERE lower(owner || '/' || name) = lower(?)", (full_name,)
        ).fetchone()

    if not repo:
        return {"ignored": f"repository '{full_name}' is not tracked"}
    if ref != f"refs/heads/{repo['branch']}":
        return {"ignored": f"push to '{ref}', tracking '{repo['branch']}'"}
    if payload.get("deleted") or set(after) == {"0"}:
        return {"ignored": "branch deleted"}

    last_webhook_at[repo["id"]] = db.utc_now()
    background.add_task(process_push, repo["id"], after)
    log.info("Webhook push for %s -> %s, assessing", full_name, after[:7])
    return {"accepted": True, "repo_id": repo["id"], "commit_sha": after}
