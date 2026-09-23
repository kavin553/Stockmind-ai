"""SQLAlchemy engine / session management.

The application targets PostgreSQL. Tests may point ``DATABASE_URL`` at SQLite
in-memory so the pure-logic and API layers can be exercised without a live database.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # Single shared connection for in-memory databases across threads.
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": __import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
        }
    return {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}


engine: Engine = create_engine(settings.database_url, echo=settings.sql_echo, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - test helper
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts and services."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
