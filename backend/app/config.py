"""All settings come from the root .env file, read once here."""
import os
import ssl
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


# LLM
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()  # groq | ollama
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
LLM_MODEL_FAST = os.getenv("LLM_MODEL_FAST", "openai/gpt-oss-20b")
LLM_TPM_LIMIT = _int("LLM_TPM_LIMIT", 8000)
LLM_TPD_LIMIT = _int("LLM_TPD_LIMIT", 200000)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")

# GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
POLL_INTERVAL_SECONDS = _int("POLL_INTERVAL_SECONDS", 30)

# App
DATABASE_PATH = ROOT_DIR / os.getenv("DATABASE_PATH", "database/career_coach.db")
MAX_FILES_PER_SNAPSHOT = _int("MAX_FILES_PER_SNAPSHOT", 60)
MAX_FILE_BYTES = _int("MAX_FILE_BYTES", 100000)
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

HTTP_USER_AGENT = "ai-career-coach/0.1"
# Trust the OS certificate store (needed when antivirus/proxy software inspects HTTPS).
SSL_CONTEXT = ssl.create_default_context()
