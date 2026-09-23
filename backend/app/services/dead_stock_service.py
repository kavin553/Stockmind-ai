"""DEAD STOCK DETECTION ENGINE (a service, **not** an AI agent).

Two halves:

* pure functions — aging, velocity, triggers, risk score, risk band. Unit-tested directly.
* database functions — candidate queries, case creation, dashboard KPI aggregation.

A product becomes a recovery candidate when it ages past ``AGING_DAYS``, has not sold for
``NO_SALE_DAYS``, holds materially more stock than predicted demand, or shows a material
velocity decline.

**Low stock is never dead stock**: low stock is not one of the triggers, and the excess
trigger cannot fire when stock sits below predicted demand.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.config import policy as default_policy
from app.models import Inventory, Product, RecoveryCase, Sale, Store
from app.schemas.domain import InventoryMetrics, PolicySpec, SalePoint


# --------------------------------------------------------------------------- pure logic


def age_days(first_received_at: date, as_of: date) -> int:
    return max(0, (as_of - first_received_at).days)


def days_since_last_sale(last_sold_at: date | None, first_received_at: date, as_of: date) -> int:
    """Days since the last sale; falls back to inventory age when it never sold."""
    if last_sold_at is None:
        return age_days(first_received_at, as_of)
    return max(0, (as_of - last_sold_at).days)


def sales_velocity(sales: list[SalePoint], as_of: date, window_days: int) -> float:
    if window_days <= 0:
        return 0.0
    total = 0.0
    for sale in sales:
        delta = (as_of - sale.sold_on).days
        if 0 <= delta < window_days:
            total += sale.quantity
    return total / window_days


def velocity_decline(velocity_recent: float, velocity_long: float) -> float:
    """Fractional decline of recent velocity vs. the long-run baseline (0 when growing)."""
    if velocity_long <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - velocity_recent / velocity_long))


def compute_excess(quantity: int, forecast_30d: float, multiplier: float) -> tuple[float, float]:
    """Excess units beyond ``multiplier`` × predicted 30-day demand, and the stock/demand ratio."""
    demand = max(0.0, forecast_30d)
    excess_units = quantity - multiplier * demand if demand > 0 else float(quantity)
    excess_ratio = (quantity / demand) if demand > 0 else (float("inf") if quantity > 0 else 0.0)
    return round(max(0.0, excess_units), 2), excess_ratio


def detect_triggers(
    *,
    age: int,
    no_sale: int,
    excess_ratio: float,
    decline: float,
    history_days: int,
    policy: PolicySpec | None = None,
) -> list[str]:
    p = policy or PolicySpec()
    triggers: list[str] = []
    if age >= p.aging_days:
        triggers.append("aging")
    if no_sale >= p.no_sale_days:
        triggers.append("no_sale")
    if excess_ratio >= p.excess_stock_multiplier:
        triggers.append("excess")
    if decline >= 0.4 and history_days >= 14:
        triggers.append("velocity_decline")
    return triggers


def risk_score(
    *,
    age: int,
    no_sale: int,
    excess_ratio: float,
    decline: float,
    policy: PolicySpec | None = None,
) -> float:
    """Weighted, bounded, and monotonic in each risk driver."""
    p = policy or PolicySpec()
    aging_component = min(1.0, age / max(1, p.aging_days * 3))
    no_sale_component = min(1.0, no_sale / max(1, p.no_sale_days * 3))
    if excess_ratio == float("inf"):
        excess_component = 1.0
    else:
        span = max(0.5, p.excess_stock_multiplier * 1.6 - 1.0)
        excess_component = max(0.0, min(1.0, (excess_ratio - 1.0) / span))
    decline_component = max(0.0, min(1.0, decline))
    score = (
        0.30 * aging_component
        + 0.30 * no_sale_component
        + 0.25 * excess_component
        + 0.15 * decline_component
    )
    return round(max(0.0, min(1.0, score)), 4)


RISK_BAND_THRESHOLDS = {
    "healthy": 0.25,
    "watch": 0.45,
    "at_risk": 0.70,
    "critical": 1.01,
}


def risk_band(score: float, policy: PolicySpec | None = None) -> str:
    """Map a 0..1 risk score onto a band. Lower score = healthier."""
    for band in ("healthy", "watch", "at_risk", "critical"):
        if score < RISK_BAND_THRESHOLDS[band]:
            return band
    return "critical"


def is_low_stock(quantity: int, velocity_30d: float, cover_days: int = 7) -> bool:
    """Low stock = less than a week of cover at current velocity. This never triggers recovery."""
    return quantity <= max(2, velocity_30d * cover_days)


def compute_metrics(
    *,
    quantity: int,
    unit_cost: float,
    first_received_at: date,
    last_sold_at: date | None,
    sales: list[SalePoint],
    forecast_30d: float,
    as_of: date,
    policy: PolicySpec | None = None,
) -> InventoryMetrics:
    """Assemble the full metric block used by the KPI layer and every agent."""
    p = policy or PolicySpec()
    age = age_days(first_received_at, as_of)
    no_sale = days_since_last_sale(last_sold_at, first_received_at, as_of)
    v30 = sales_velocity(sales, as_of, 30)
    v90 = sales_velocity(sales, as_of, 90)
    decline = velocity_decline(v30, v90)
    excess_units, excess_ratio = compute_excess(quantity, forecast_30d, p.excess_stock_multiplier)
    history_days = 0
    if sales:
        history_days = (as_of - min(s.sold_on for s in sales)).days

    triggers = detect_triggers(
        age=age,
        no_sale=no_sale,
        excess_ratio=excess_ratio,
        decline=decline,
        history_days=history_days,
        policy=p,
    )
    score = risk_score(age=age, no_sale=no_sale, excess_ratio=excess_ratio, decline=decline, policy=p)
    capital_locked = round(quantity * unit_cost, 2)
    return InventoryMetrics(
        age_days=age,
        days_since_sale=no_sale,
        sales_velocity_30d=round(v30, 4),
        sales_velocity_90d=round(v90, 4),
        velocity_decline=round(decline, 4),
        excess_units=excess_units,
        excess_ratio=round(excess_ratio, 4) if excess_ratio != float("inf") else 9999.0,
        risk_score=score,
        risk_band=risk_band(score, p),
        capital_locked=capital_locked,
        capital_at_risk=round(capital_locked * score, 2),
        triggers=triggers,
    )


def is_recovery_candidate(metrics: InventoryMetrics, quantity: int) -> bool:
    """A candidate needs stock *and* at least one dead-stock trigger.

    Low stock is explicitly **not** a recovery problem: a thin, actively-selling SKU is a
    replenishment problem, so it is excluded even if it is old. The recovery engine exists to
    dispose of surplus, not to chase items that are about to sell out.
    """
    if quantity <= 0 or not metrics.triggers:
        return False
    if metrics.sales_velocity_30d > 0 and is_low_stock(quantity, metrics.sales_velocity_30d):
        return False
    return True


# --------------------------------------------------------------------------- db queries


def _inventory_query(store_id: uuid.UUID | None = None, category_id: uuid.UUID | None = None) -> Select:
    stmt = select(Inventory).join(Product, Product.id == Inventory.product_id)
    if store_id:
        stmt = stmt.where(Inventory.store_id == store_id)
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    return stmt


def load_sales(db: Session, product_id: uuid.UUID, store_id: uuid.UUID, days: int = 400) -> list[Sale]:
    cutoff = date.today()
    return list(
        db.scalars(
            select(Sale)
            .where(
                Sale.product_id == product_id,
                Sale.store_id == store_id,
                Sale.sold_on >= date.fromordinal(cutoff.toordinal() - days),
            )
            .order_by(Sale.sold_on)
        )
    )


def to_sale_points(sales: list[Sale]) -> list[SalePoint]:
    return [
        SalePoint(
            sold_on=s.sold_on,
            quantity=s.quantity,
            unit_price=float(s.unit_price),
            is_promotion=s.is_promotion,
        )
        for s in sales
    ]


def get_or_create_case(
    db: Session,
    *,
    product: Product,
    store: Store,
    inventory: Inventory,
    metrics: InventoryMetrics,
    forecast_30d: float,
) -> RecoveryCase:
    case = db.scalars(
        select(RecoveryCase).where(
            RecoveryCase.product_id == product.id,
            RecoveryCase.store_id == store.id,
            RecoveryCase.status.in_(("open", "planned")),
        )
    ).first()
    capital_locked = Decimal(str(metrics.capital_locked))
    values = dict(
        triggers=metrics.triggers,
        age_days=metrics.age_days,
        days_since_sale=metrics.days_since_sale,
        forecast_30d=Decimal(str(round(forecast_30d, 2))),
        excess_units=Decimal(str(metrics.excess_units)),
        stock_units=inventory.quantity,
        capital_locked=capital_locked,
        capital_at_risk=Decimal(str(metrics.capital_at_risk)),
        risk_score=Decimal(str(metrics.risk_score)),
        risk_band=metrics.risk_band,
    )
    if case is None:
        case = RecoveryCase(product_id=product.id, store_id=store.id, status="open", **values)
        db.add(case)
    else:
        for key, value in values.items():
            setattr(case, key, value)
    db.flush()
    return case


def dashboard_kpis(db: Session) -> dict:
    """Every KPI is aggregated from rows — nothing here is hardcoded."""
    inventory_rows = list(db.scalars(select(Inventory).join(Product, Product.id == Inventory.product_id)))
    total_value = 0.0
    dead_value = 0.0
    dead_units = 0
    capital_at_risk = 0.0
    storage_total = 0.0
    storage_dead = 0.0
    ages: list[int] = []
    critical = 0

    for row in inventory_rows:
        product = row.product
        unit_cost = float(product.unit_cost)
        value = row.quantity * unit_cost
        total_value += value
        dims = product.dimensions_cm or {}
        volume = (
            float(dims.get("l", 0)) * float(dims.get("w", 0)) * float(dims.get("h", 0)) / 1_000_000.0
        )
        storage_total += volume * row.quantity

        age = age_days(row.first_received_at, date.today())
        ages.append(age)
        sales = to_sale_points(load_sales(db, row.product_id, row.store_id, days=200))
        forecast_30d = _cached_forecast_30d(db, row.product_id, row.store_id)
        metrics = compute_metrics(
            quantity=row.quantity,
            unit_cost=unit_cost,
            first_received_at=row.first_received_at,
            last_sold_at=row.last_sold_at,
            sales=sales,
            forecast_30d=forecast_30d,
            as_of=date.today(),
        )
        if is_recovery_candidate(metrics, row.quantity):
            dead_value += value
            dead_units += row.quantity
            capital_at_risk += metrics.capital_at_risk
            storage_dead += volume * row.quantity
            if metrics.risk_band == "critical":
                critical += 1

    dead_pct = (dead_value / total_value) if total_value > 0 else 0.0
    avg_age = (sum(ages) / len(ages)) if ages else 0.0

    executed = db.scalar(select(func.count()).select_from(RecoveryCase).where(RecoveryCase.status.in_(("executed", "verified")))) or 0
    total_cases = db.scalar(select(func.count()).select_from(RecoveryCase)) or 0

    return {
        "current_inventory_value": round(total_value, 2),
        "dead_stock_value": round(dead_value, 2),
        "dead_stock_units": dead_units,
        "dead_stock_pct": round(dead_pct, 4),
        "capital_locked": round(dead_value, 2),
        "capital_at_risk": round(capital_at_risk, 2),
        "avg_inventory_age_days": round(avg_age, 1),
        "critical_skus": critical,
        "recovery_rate": round(executed / total_cases, 4) if total_cases else 0.0,
        "storage_volume_m3": round(storage_total, 4),
        "dead_stock_storage_m3": round(storage_dead, 4),
    }


def _cached_forecast_30d(db: Session, product_id: uuid.UUID, store_id: uuid.UUID) -> float:
    from app.models import Forecast

    row = db.scalars(
        select(Forecast)
        .where(Forecast.product_id == product_id, Forecast.store_id == store_id, Forecast.horizon_days == 30)
        .order_by(Forecast.as_of.desc())
    ).first()
    return float(row.predicted_units) if row else 0.0


def dead_stock_rows(db: Session, *, store_id=None, category_id=None, risk_band=None, limit=200) -> list[dict]:
    """Row-level dead-stock feed for the Dead Stock Center table."""
    stmt = _inventory_query(store_id, category_id).order_by(Inventory.quantity.desc()).limit(limit)
    rows = []
    for inv in db.scalars(stmt):
        product = inv.product
        sales = to_sale_points(load_sales(db, inv.product_id, inv.store_id, days=200))
        forecast_30d = _cached_forecast_30d(db, inv.product_id, inv.store_id)
        metrics = compute_metrics(
            quantity=inv.quantity,
            unit_cost=float(product.unit_cost),
            first_received_at=inv.first_received_at,
            last_sold_at=inv.last_sold_at,
            sales=sales,
            forecast_30d=forecast_30d,
            as_of=date.today(),
        )
        if not is_recovery_candidate(metrics, inv.quantity):
            continue
        if risk_band and metrics.risk_band != risk_band:
            continue
        rows.append(
            {
                "product_id": str(product.id),
                "store_id": str(inv.store_id),
                "sku": product.sku,
                "name": product.name,
                "category": product.category.name,
                "store": inv.store.code,
                "quantity": inv.quantity,
                "age_days": metrics.age_days,
                "days_since_sale": metrics.days_since_sale,
                "forecast_30d": forecast_30d,
                "risk_band": metrics.risk_band,
                "risk_score": metrics.risk_score,
                "capital_locked": metrics.capital_locked,
                "capital_at_risk": metrics.capital_at_risk,
                "excess_units": metrics.excess_units,
                "triggers": metrics.triggers,
            }
        )
    rows.sort(key=lambda r: r["risk_score"] * r["capital_locked"], reverse=True)
    return rows
