-- AI Career Coach schema. Safe to run repeatedly (IF NOT EXISTS everywhere).

CREATE TABLE IF NOT EXISTS jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type  TEXT NOT NULL CHECK (source_type IN ('greenhouse', 'lever', 'manual')),
    source_url   TEXT NOT NULL UNIQUE,
    company      TEXT,
    title        TEXT,
    location     TEXT,
    raw_text     TEXT NOT NULL,
    fetched_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL UNIQUE,
    label       TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'other',
    synonyms    TEXT NOT NULL DEFAULT '[]',   -- JSON array
    rule_hints  TEXT,                         -- JSON object or NULL
    created_by  TEXT NOT NULL CHECK (created_by IN ('seed', 'llm'))
);

CREATE TABLE IF NOT EXISTS job_requirements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill_id        INTEGER NOT NULL REFERENCES skills(id),
    importance      TEXT NOT NULL CHECK (importance IN ('required', 'preferred')),
    source_quote    TEXT NOT NULL,
    quote_verified  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (job_id, skill_id)
);

CREATE TABLE IF NOT EXISTS repos (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    owner            TEXT NOT NULL,
    name             TEXT NOT NULL,
    branch           TEXT NOT NULL,
    last_seen_sha    TEXT,
    etag             TEXT,
    polling_enabled  INTEGER NOT NULL DEFAULT 1,
    last_polled_at   TEXT,
    created_at       TEXT NOT NULL,
    UNIQUE (owner, name, branch)
);

CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id         INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    commit_sha      TEXT NOT NULL,
    commit_message  TEXT,
    committed_at    TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE (repo_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS snapshot_files (
    snapshot_id  INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    path         TEXT NOT NULL,
    blob_sha     TEXT NOT NULL,
    size         INTEGER NOT NULL,
    included     INTEGER NOT NULL,
    skip_reason  TEXT,
    PRIMARY KEY (snapshot_id, path)
);

-- File contents by Git blob SHA: identical content is fetched from GitHub only once.
CREATE TABLE IF NOT EXISTS blobs (
    blob_sha   TEXT PRIMARY KEY,
    content    TEXT,                       -- NULL when binary/undecodable
    is_binary  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id          INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
    snapshot_id      INTEGER NOT NULL REFERENCES snapshots(id),
    prev_run_id      INTEGER REFERENCES runs(id),
    trigger          TEXT NOT NULL CHECK (trigger IN ('initial', 'poll', 'webhook', 'manual', 'new_skills')),
    changed_files    TEXT NOT NULL DEFAULT '[]',  -- JSON array
    affected_skills  TEXT NOT NULL DEFAULT '[]',  -- JSON array of skill keys
    status           TEXT NOT NULL CHECK (status IN ('running', 'done', 'failed')),
    error            TEXT,
    started_at       TEXT NOT NULL,
    finished_at      TEXT
);

CREATE TABLE IF NOT EXISTS skill_results (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id               INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    skill_id             INTEGER NOT NULL REFERENCES skills(id),
    status               TEXT NOT NULL CHECK (status IN ('demonstrated', 'partially_demonstrated', 'not_demonstrated')),
    confidence           TEXT CHECK (confidence IN ('low', 'medium', 'high')),
    rationale            TEXT,
    method               TEXT NOT NULL CHECK (method IN ('rules', 'llm', 'rules+llm')),
    carried_from_run_id  INTEGER REFERENCES runs(id),
    UNIQUE (run_id, skill_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_result_id  INTEGER NOT NULL REFERENCES skill_results(id) ON DELETE CASCADE,
    path             TEXT NOT NULL,
    start_line       INTEGER,
    end_line         INTEGER,
    snippet          TEXT,
    commit_sha       TEXT NOT NULL,
    permalink        TEXT NOT NULL,
    source           TEXT NOT NULL CHECK (source IN ('rule', 'llm')),
    verified         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key       TEXT PRIMARY KEY,
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    response        TEXT NOT NULL,   -- JSON
    tokens_used     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    delivery_id  TEXT PRIMARY KEY,
    received_at  TEXT NOT NULL
);
