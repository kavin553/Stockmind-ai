"""AUDIT SERVICE — append-only trail.

Every detection, agent evaluation, decision, guardrail outcome and execution writes a row
here. Rows are never updated or deleted.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.models.base import utcnow

__all__ = ["record", "list_entries", "utcnow"]


def record(
    db: Session,
    *,
    actor: str = "system",
    actor_type: str = "system",
    sku: str = "",
    trigger: str = "",
    agent: str | None = None,
    decision: str = "",
    inputs_summary: dict | None = None,
    recommendation: dict | None = None,
    confidence: float = 0.0,
    execution_result: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        actor_type=actor_type,
        sku=sku,
        trigger=trigger,
        agent=agent,
        decision=decision,
        inputs_summary=inputs_summary or {},
        recommendation=recommendation or {},
        confidence=Decimal(str(round(float(confidence), 4))),
        execution_result=execution_result or {},
    )
    db.add(entry)
    db.flush()
    return entry


def list_entries(db: Session, limit: int = 100, sku: str | None = None) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).limit(limit)
    if sku:
        stmt = stmt.where(AuditLog.sku == sku)
    return list(db.scalars(stmt))
