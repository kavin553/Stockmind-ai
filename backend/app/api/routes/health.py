from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health/live")
def liveness() -> dict:
    return {"status": "ok", "version": settings.version}


@router.get("/health")
def health(db: Session = Depends(db_session)) -> dict:
    database = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on environment
        database = f"error: {type(exc).__name__}"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "version": settings.version,
        "environment": settings.environment,
    }
