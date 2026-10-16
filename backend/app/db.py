"""SQLite access. One short-lived connection per unit of work."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app import config

SCHEMA_PATH = config.ROOT_DIR / "database" / "schema.sql"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    from app.skills.taxonomy import seed_skills

    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with transaction() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        seed_skills(conn)
