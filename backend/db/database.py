"""
Database setup.
Supports both SQLite (local dev) and PostgreSQL.
"""
import logging
import os

from sqlalchemy import create_engine, event
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

DATABASE_ENV_NAMES = [
    "DATABASE_URL",
    "RENDER_DATABASE_URL",
    "POSTGRES_URL",
    "DATABASE_URI",
    "SQLALCHEMY_DATABASE_URL",
]


def get_database_url():
    for name in DATABASE_ENV_NAMES:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip(), name
    return "sqlite:///./lens_inspections.db", "sqlite_default"

DATABASE_URL, DATABASE_SOURCE = get_database_url()

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_SOURCE == "sqlite_default":
    logger.warning("Using local SQLite fallback because no database environment variable was set.")

IS_SQLITE = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if IS_SQLITE else {}

try:
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
except ArgumentError as exc:
    raise RuntimeError(
        f"Invalid database URL from {DATABASE_SOURCE}: {DATABASE_URL!r}. "
        "Set a valid DATABASE_URL or RENDER_DATABASE_URL in Render."
    ) from exc

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Enable WAL mode for SQLite to prevent lock contention under concurrent writes
if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _set_wal(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA synchronous=NORMAL")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
