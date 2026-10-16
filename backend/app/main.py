import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app import config, db
from app.assessment.routes import router as assessments_router
from app.github.routes import router as repos_router
from app.jobs.routes import router as jobs_router
from app.llm.rate_limit import limiter
from app.schemas import Skill
from app.skills.taxonomy import list_skills

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    with db.transaction() as conn:
        used = conn.execute(
            "SELECT COALESCE(SUM(tokens_used), 0) FROM llm_cache WHERE substr(created_at, 1, 10) = ?",
            (db.utc_now()[:10],),
        ).fetchone()[0]
    limiter.set_used_today(used)
    yield


app = FastAPI(title="AI Career Coach", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(jobs_router)
app.include_router(repos_router)
app.include_router(assessments_router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "llm_provider": config.LLM_PROVIDER,
        "llm_key_configured": bool(config.GROQ_API_KEY) or config.LLM_PROVIDER == "ollama",
        "github_token_configured": bool(config.GITHUB_TOKEN),
        "tokens_used_today": limiter.used_today,
        "poller": "not started",
    }


@app.get("/api/skills", response_model=list[Skill])
def skills():
    with db.transaction() as conn:
        return [dict(s) for s in list_skills(conn)]
