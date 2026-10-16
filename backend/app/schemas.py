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


class Skill(BaseModel):
    key: str
    label: str
    category: str
    created_by: str
