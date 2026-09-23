from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamped, UUIDPrimaryKey, utcnow


class Forecast(UUIDPrimaryKey, Base):
    __tablename__ = "forecasts"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"), index=True)
    as_of: Mapped[date] = mapped_column(Date)
    horizon_days: Mapped[int] = mapped_column(Integer)
    predicted_units: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    method: Mapped[str] = mapped_column(String(32), default="category_baseline")
    model_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("product_id", "store_id", "as_of", "horizon_days", name="uq_forecast_key"),
    )


class RecoveryCase(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "recovery_cases"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"), index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    triggers: Mapped[list] = mapped_column(JSON, default=list)
    age_days: Mapped[int] = mapped_column(Integer, default=0)
    days_since_sale: Mapped[int] = mapped_column(Integer, default=0)
    forecast_30d: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    excess_units: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    stock_units: Mapped[int] = mapped_column(Integer, default=0)
    capital_locked: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    capital_at_risk: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    risk_band: Mapped[str] = mapped_column(String(16), default="watch", index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)

    agent_results: Mapped[list["AgentResult"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    plans: Mapped[list["RecoveryPlan"]] = relationship(back_populates="case", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_recovery_cases_product_store", "product_id", "store_id"),)


class AgentResult(UUIDPrimaryKey, Base):
    __tablename__ = "agent_results"

    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recovery_cases.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(32), index=True)
    feasible: Mapped[bool] = mapped_column(Boolean, default=False)
    reason_unavailable: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_units_cleared: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    expected_recovery: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    expected_loss: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    action_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    expected_net_recovery: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[RecoveryCase] = relationship(back_populates="agent_results")

    __table_args__ = (Index("ix_agent_results_case_agent", "case_id", "agent"),)


class RecoveryPlan(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "recovery_plans"

    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recovery_cases.id", ondelete="CASCADE"), index=True)
    strategy: Mapped[str] = mapped_column(String(16), default="single")
    allocations: Mapped[list] = mapped_column(JSON, default=list)
    expected_recovery: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    expected_loss: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    total_action_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    expected_net_recovery: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    guardrail_status: Mapped[str] = mapped_column(String(16), default="pending")
    guardrail_findings: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="planned", index=True)

    case: Mapped[RecoveryCase] = relationship(back_populates="plans")
    actions: Mapped[list["Action"]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class Action(UUIDPrimaryKey, Base):
    __tablename__ = "actions"

    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recovery_plans.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recovery_cases.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(32))
    units: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    plan: Mapped[RecoveryPlan] = relationship(back_populates="actions")
    results: Mapped[list["ActionResult"]] = relationship(back_populates="action", cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint("units >= 0", name="ck_actions_units_non_negative"),)


class ActionResult(UUIDPrimaryKey, Base):
    __tablename__ = "action_results"

    action_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actions.id", ondelete="CASCADE"), index=True)
    predicted_units: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    simulated_units: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    predicted_recovery: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    simulated_recovery: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    variance_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))
    label: Mapped[str] = mapped_column(String(32), default="prototype_simulation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    action: Mapped[Action] = relationship(back_populates="results")


class VerificationResult(UUIDPrimaryKey, Base):
    __tablename__ = "verification_results"

    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recovery_plans.id", ondelete="CASCADE"), index=True)
    predicted_units: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    simulated_units: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    predicted_recovery: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    simulated_recovery: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    units_variance_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))
    recovery_variance_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))
    label: Mapped[str] = mapped_column(String(32), default="prototype_simulation")
    simulated_window: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Promotion(UUIDPrimaryKey, Base):
    __tablename__ = "promotions"

    kind: Mapped[str] = mapped_column(String(24))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    anchor_product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stores.id"), nullable=True)
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("0"))
    incentive: Mapped[str] = mapped_column(String(16), default="none")
    bundle_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by_action_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StoreTransfer(UUIDPrimaryKey, Base):
    __tablename__ = "store_transfers"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    source_store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"), index=True)
    destination_store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    transfer_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(16), default="planned")
    created_by_action_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        CheckConstraint("source_store_id <> destination_store_id", name="ck_transfer_distinct_stores"),
        CheckConstraint("quantity > 0", name="ck_transfer_quantity_positive"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(160), default="system")
    actor_type: Mapped[str] = mapped_column(String(16), default="system")
    sku: Mapped[str] = mapped_column(String(32), default="", index=True)
    trigger: Mapped[str] = mapped_column(String(64), default="")
    agent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision: Mapped[str] = mapped_column(String(64), default="")
    inputs_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendation: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    execution_result: Mapped[dict] = mapped_column(JSON, default=dict)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
