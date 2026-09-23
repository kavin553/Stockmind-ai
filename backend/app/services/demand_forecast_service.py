"""DEMAND FORECAST SERVICE (a service, not an agent).

Bridges the database to the ML layer: assembles the daily series, trains/serves the model,
persists :class:`Forecast` rows and returns a :class:`ForecastBundle`.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import policy
from app.ml.features import StaticFeatures, daily_series
from app.ml.forecast import forecast_bundle
from app.models import Forecast, Inventory, Product, Sale, Store
from app.schemas.domain import ForecastBundle


def stable_code(value: str, buckets: int = 512) -> int:
    """Deterministic integer code for a categorical id (never Python's salted hash)."""
    digest = hashlib.sha256(value.encode()).hexdigest()
    return int(digest[:8], 16) % buckets


def sales_series(db: Session, product_id: uuid.UUID, store_id: uuid.UUID, days: int = 540) -> pd.Series:
    since = date.today() - timedelta(days=days)
    sales = db.scalars(
        select(Sale).where(Sale.product_id == product_id, Sale.store_id == store_id, Sale.sold_on >= since)
    )
    return daily_series(sales, date.today(), days)


def category_daily_series(
    db: Session, category_id: uuid.UUID, store_id: uuid.UUID, days: int = 180
) -> pd.Series:
    """Average per-product daily units for the category — the cold-start baseline."""
    product_ids = list(db.scalars(select(Product.id).where(Product.category_id == category_id)))
    if not product_ids:
        return pd.Series(0.0, index=pd.date_range(end=pd.Timestamp(date.today()), periods=days, freq="D"))
    since = date.today() - timedelta(days=days)
    sales = db.scalars(
        select(Sale).where(
            Sale.product_id.in_(product_ids), Sale.store_id == store_id, Sale.sold_on >= since
        )
    )
    total = daily_series(sales, date.today(), days)
    return total / max(1, len(product_ids))


def _static(product: Product, store: Store, inventory: Inventory) -> StaticFeatures:
    return StaticFeatures(
        current_stock=inventory.quantity,
        inventory_age=(date.today() - inventory.first_received_at).days,
        selling_price=float(product.list_price),
        discount_pct=float(inventory.discount_pct),
        category_code=stable_code(str(product.category_id)),
        store_code=stable_code(str(store.id)),
    )


def forecast_for(
    db: Session,
    product: Product,
    store: Store,
    inventory: Inventory,
    *,
    as_of: date | None = None,
    persist: bool = True,
) -> ForecastBundle:
    as_of = as_of or date.today()
    series = sales_series(db, product.id, store.id)
    category_series = category_daily_series(db, product.category_id, store.id)
    result = forecast_bundle(
        series=series,
        static=_static(product, store, inventory),
        as_of=as_of,
        horizons=policy.forecast_horizons,
        category_daily=category_series,
    )
    predictions: dict[int, float] = result["predictions"]
    bundle = ForecastBundle(
        forecast_7d=predictions.get(7, 0.0),
        forecast_30d=predictions.get(30, 0.0),
        forecast_60d=predictions.get(60, 0.0),
        confidence=float(result["confidence"]),
        method=str(result["method"]),
        as_of=as_of,
        model_metrics=result.get("metrics"),
    )
    if persist:
        _persist(db, product.id, store.id, as_of, predictions, bundle)
    return bundle


def _persist(
    db: Session,
    product_id: uuid.UUID,
    store_id: uuid.UUID,
    as_of: date,
    predictions: dict[int, float],
    bundle: ForecastBundle,
) -> None:
    for horizon, units in predictions.items():
        existing = db.scalars(
            select(Forecast).where(
                Forecast.product_id == product_id,
                Forecast.store_id == store_id,
                Forecast.as_of == as_of,
                Forecast.horizon_days == horizon,
            )
        ).first()
        if existing:
            existing.predicted_units = units
            existing.confidence = bundle.confidence
            existing.method = bundle.method
            existing.model_metrics = bundle.model_metrics
        else:
            db.add(
                Forecast(
                    product_id=product_id,
                    store_id=store_id,
                    as_of=as_of,
                    horizon_days=horizon,
                    predicted_units=units,
                    confidence=bundle.confidence,
                    method=bundle.method,
                    model_metrics=bundle.model_metrics,
                )
            )
    db.flush()


def cached_forecast_30d(db: Session, product_id: uuid.UUID, store_id: uuid.UUID) -> float:
    row = db.scalars(
        select(Forecast)
        .where(Forecast.product_id == product_id, Forecast.store_id == store_id, Forecast.horizon_days == 30)
        .order_by(Forecast.as_of.desc())
    ).first()
    return float(row.predicted_units) if row else 0.0
