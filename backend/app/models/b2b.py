from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped, UUIDPrimaryKey, utcnow


class B2BBuyer(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "b2b_buyers"

    business_name: Mapped[str] = mapped_column(String(160), index=True)
    contact_name: Mapped[str] = mapped_column(String(120), default="")
    required_categories: Mapped[list] = mapped_column(JSON, default=list)
    location_city: Mapped[str] = mapped_column(String(80), default="")
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    lon: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    required_quantity: Mapped[int] = mapped_column(Integer, default=1)
    maximum_budget: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    preferred_unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    reliability_score: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("0.700"))
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("required_quantity > 0", name="ck_buyers_quantity_positive"),
        CheckConstraint("maximum_budget >= 0", name="ck_buyers_budget_non_negative"),
    )


class B2BOrder(UUIDPrimaryKey, Base):
    __tablename__ = "b2b_orders"

    buyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("b2b_buyers.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_by_action_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),)
