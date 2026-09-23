from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamped, UUIDPrimaryKey


class Store(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "stores"

    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80))
    region: Mapped[str] = mapped_column(String(80), default="")
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    lon: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    inventory: Mapped[list["Inventory"]] = relationship(back_populates="store")  # noqa: F821


class Category(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    # Price elasticity used by the Discount Agent's lift curve.
    elasticity: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("1.100"))
    # category name -> affinity 0..1, used by the Buy-A-Get-B agent.
    co_purchase_affinity: Mapped[dict] = mapped_column(JSON, default=dict)

    products: Mapped[list["Product"]] = relationship(back_populates="category")  # noqa: F821


class Product(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), index=True)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    list_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    b2b_floor_pct: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("0.800"))
    dimensions_cm: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    category: Mapped[Category] = relationship(back_populates="products")
    inventory: Mapped[list["Inventory"]] = relationship(back_populates="product")  # noqa: F821

    __table_args__ = (
        CheckConstraint("unit_cost > 0", name="ck_products_cost_positive"),
        CheckConstraint("list_price > 0", name="ck_products_price_positive"),
    )


class Inventory(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "inventory"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 3), default=Decimal("0"))
    first_received_at: Mapped[date] = mapped_column(Date)
    last_sold_at: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    location_code: Mapped[str] = mapped_column(String(24), default="UNASSIGNED")
    updated_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    product: Mapped[Product] = relationship(back_populates="inventory")
    store: Mapped[Store] = relationship(back_populates="inventory")

    __table_args__ = (
        UniqueConstraint("product_id", "store_id", name="uq_inventory_product_store"),
        CheckConstraint("quantity >= 0", name="ck_inventory_quantity_non_negative"),
        CheckConstraint("discount_pct >= 0 AND discount_pct <= 0.95", name="ck_inventory_discount_range"),
    )


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"), index=True)
    sold_on: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_promotion: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_sales_product_store_date", "product_id", "store_id", "sold_on"),
        CheckConstraint("quantity > 0", name="ck_sales_quantity_positive"),
    )


class User(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32), default="inventory_staff")
    store_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stores.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
