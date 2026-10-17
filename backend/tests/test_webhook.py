import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.watch import webhook

SECRET = "test-secret"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "GITHUB_WEBHOOK_SECRET", SECRET)
    db.init_db()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO repos (owner, name, branch, created_at) VALUES ('me', 'demo', 'main', ?)",
            (db.utc_now(),),
        )
    calls = []
    monkeypatch.setattr(webhook, "process_push", lambda repo_id, sha: calls.append((repo_id, sha)))
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(webhook.router)
    c = TestClient(app)
    c.calls = calls
    return c


def send(client, payload, event="push", delivery="d1", secret=SECRET):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/api/webhooks/github", content=body, headers={
        "X-GitHub-Event": event, "X-GitHub-Delivery": delivery, "X-Hub-Signature-256": sig,
        "Content-Type": "application/json"})


PUSH = {"ref": "refs/heads/main", "after": "abc1234def", "repository": {"full_name": "Me/Demo"}}


def test_valid_push_is_accepted(client):
    r = send(client, PUSH)
    assert r.status_code == 202 and r.json()["accepted"]
    assert client.calls == [(1, "abc1234def")]


def test_bad_signature_rejected(client):
    assert send(client, PUSH, secret="wrong").status_code == 401
    assert client.calls == []


def test_ping(client):
    r = send(client, {"zen": "hi"}, event="ping")
    assert r.status_code == 200 and r.json()["event"] == "ping"


def test_duplicate_delivery_ignored(client):
    send(client, PUSH, delivery="same")
    r = send(client, PUSH, delivery="same")
    assert r.json() == {"ignored": "duplicate delivery"}
    assert len(client.calls) == 1


def test_other_branch_and_untracked_repo_ignored(client):
    assert "ignored" in send(client, {**PUSH, "ref": "refs/heads/dev"}, delivery="a").json()
    assert "ignored" in send(client, {**PUSH, "repository": {"full_name": "x/y"}}, delivery="b").json()
    assert client.calls == []


def test_signature_helper():
    body = b"{}"
    good = "sha256=" + hmac.new(b"s", body, hashlib.sha256).hexdigest()
    assert webhook.verify_signature("s", body, good)
    assert not webhook.verify_signature("", body, good)
    assert not webhook.verify_signature("s", body, None)
