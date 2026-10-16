"""All GitHub REST API calls live here."""
import base64
import re
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app import config

API = "https://api.github.com"


class GitHubError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class Head:
    sha: str
    message: str
    committed_at: str
    etag: str | None


def _client() -> httpx.Client:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": config.HTTP_USER_AGENT,
    }
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return httpx.Client(base_url=API, headers=headers, timeout=30, verify=config.SSL_CONTEXT)


def _check(resp: httpx.Response, what: str) -> None:
    if resp.status_code == 404:
        raise GitHubError(404, f"{what} not found (is the repository public and the name correct?)")
    if resp.status_code in (401, 403):
        detail = resp.json().get("message", "") if resp.content else ""
        raise GitHubError(502, f"GitHub refused the request ({resp.status_code}): {detail}")
    if resp.status_code >= 400:
        raise GitHubError(502, f"GitHub error {resp.status_code} for {what}")


def parse_full_name(text: str) -> tuple[str, str]:
    """Accepts 'owner/name' or a github.com URL."""
    text = text.strip().removesuffix(".git").rstrip("/")
    m = re.match(r"^(?:https?://github\.com/)?([\w.-]+)/([\w.-]+)$", text)
    if not m:
        raise GitHubError(400, "Enter the repository as owner/name or a github.com URL")
    return m.group(1), m.group(2)


def get_default_branch(owner: str, name: str) -> str:
    with _client() as c:
        resp = c.get(f"/repos/{owner}/{name}")
    _check(resp, f"Repository {owner}/{name}")
    return resp.json()["default_branch"]


def get_head(owner: str, name: str, branch: str, etag: str | None = None) -> Head | None:
    """Latest commit on a branch. Returns None if unchanged since `etag` (304 is free on the rate limit)."""
    headers = {"If-None-Match": etag} if etag else {}
    with _client() as c:
        resp = c.get(f"/repos/{owner}/{name}/commits/{quote(branch, safe='')}", headers=headers)
    if resp.status_code == 304:
        return None
    _check(resp, f"Branch '{branch}' of {owner}/{name}")
    data = resp.json()
    return Head(
        sha=data["sha"],
        message=data["commit"]["message"].splitlines()[0],
        committed_at=data["commit"]["committer"]["date"],
        etag=resp.headers.get("ETag"),
    )


def get_tree(owner: str, name: str, sha: str) -> list[dict]:
    """All files at a commit: [{path, sha, size}]."""
    with _client() as c:
        resp = c.get(f"/repos/{owner}/{name}/git/trees/{sha}", params={"recursive": "1"})
    _check(resp, "Repository tree")
    return [
        {"path": e["path"], "sha": e["sha"], "size": e.get("size", 0)}
        for e in resp.json()["tree"]
        if e["type"] == "blob"
    ]


def get_blob_text(owner: str, name: str, blob_sha: str) -> str | None:
    """File content as text, or None if it is binary."""
    with _client() as c:
        resp = c.get(f"/repos/{owner}/{name}/git/blobs/{blob_sha}")
    _check(resp, f"File blob {blob_sha[:7]}")
    raw = base64.b64decode(resp.json()["content"])
    if b"\x00" in raw[:8000]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def compare(owner: str, name: str, base: str, head: str) -> list[dict]:
    """Files changed between two commits: [{path, status, previous_path}]."""
    with _client() as c:
        resp = c.get(f"/repos/{owner}/{name}/compare/{base}...{head}")
    _check(resp, "Commit comparison")
    return [
        {"path": f["filename"], "status": f["status"], "previous_path": f.get("previous_filename")}
        for f in resp.json().get("files", [])
    ]


def count_commits(owner: str, name: str, branch: str) -> int:
    """Number of commits on a branch, read from the pagination 'last' link with per_page=1."""
    with _client() as c:
        resp = c.get(f"/repos/{owner}/{name}/commits", params={"sha": branch, "per_page": 1})
    _check(resp, "Commit history")
    m = re.search(r'[?&]page=(\d+)>; rel="last"', resp.headers.get("Link", ""))
    return int(m.group(1)) if m else len(resp.json())


def permalink(owner: str, name: str, sha: str, path: str, start: int | None = None, end: int | None = None) -> str:
    url = f"https://github.com/{owner}/{name}/blob/{sha}/{quote(path)}"
    if start:
        url += f"#L{start}" + (f"-L{end}" if end and end != start else "")
    return url
