"""Request and response shapes for the API."""
from pydantic import BaseModel


class JobCreate(BaseModel):
    url: str
    text: str | None = None


class Requirement(BaseModel):
    id: int
    skill_key: str
    skill_label: str
    importance: str
    quote: str
    quote_verified: bool


class Job(BaseModel):
    id: int
    company: str | None
    title: str | None
    location: str | None
    source_url: str
    source_type: str
    fetched_at: str
    requirements: list[Requirement]
    dropped_requirements: int = 0


class JobSummary(BaseModel):
    id: int
    company: str | None
    title: str | None
    source_url: str
    requirement_count: int


class RepoCreate(BaseModel):
    full_name: str  # "owner/name" or a github.com URL
    branch: str | None = None  # defaults to the repo's default branch


class SnapshotFile(BaseModel):
    path: str
    size: int
    included: bool
    skip_reason: str | None
    url: str


class Snapshot(BaseModel):
    id: int
    commit_sha: str
    commit_message: str | None
    committed_at: str | None
    commit_url: str
    files_included: int
    files_skipped: int
    files: list[SnapshotFile]


class Repo(BaseModel):
    id: int
    full_name: str
    branch: str
    html_url: str
    polling: bool
    last_polled_at: str | None
    latest_snapshot: Snapshot | None


class Skill(BaseModel):
    key: str
    label: str
    category: str
    created_by: str
