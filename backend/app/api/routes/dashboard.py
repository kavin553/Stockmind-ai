from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session
from app.models import Forecast, Inventory, Product, RecoveryCase, Sale, User
from app.services import dead_stock_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/kpis")
def kpis(db: Session = Depends(db_session), _: User = Depends(current_user)) -> dict:
    return dead_stock_service.dashboard_kpis(db)


@router.get("")
def dashboard(db: Session = Depends(db_session), _: User = Depends(current_user)) -> dict:
    metrics = dead_stock_service.dashboard_kpis(db)

    dead_by_category: dict[str, float] = defaultdict(float)
    aging_buckets = {"0-30": 0, "31-60": 0, "61-90": 0, "91-180": 0, "180+": 0}
    strategy_counts: dict[str, int] = defaultdict(int)

    for inv in db.scalars(select(Inventory).join(Product, Product.id == Inventory.product_id)):
        product = inv.product
        age = (date.today() - inv.first_received_at).days
        if age <= 30:
            aging_buckets["0-30"] += 1
        elif age <= 60:
            aging_buckets["31-60"] += 1
        elif age <= 90:
            aging_buckets["61-90"] += 1
        elif age <= 180:
            aging_buckets["91-180"] += 1
        else:
            aging_buckets["180+"] += 1

        forecast_30d = _latest_forecast(db, inv.product_id, inv.store_id)
        sales = dead_stock_service.to_sale_points(
            dead_stock_service.load_sales(db, inv.product_id, inv.store_id, days=200)
        )
        m = dead_stock_service.compute_metrics(
            quantity=inv.quantity,
            unit_cost=float(product.unit_cost),
            first_received_at=inv.first_received_at,
            last_sold_at=inv.last_sold_at,
            sales=sales,
            forecast_30d=forecast_30d,
            as_of=date.today(),
        )
        if dead_stock_service.is_recovery_candidate(m, inv.quantity):
            dead_by_category[product.category.name] += inv.quantity * float(product.unit_cost)

    for case in db.scalars(select(RecoveryCase)):
        for row in case.agent_results:
            if row.feasible:
                strategy_counts[row.agent] += 1

    # Capital at risk over time: value that has aged past the threshold, by receipt month.
    capital_series = []
    for months_back in range(5, -1, -1):
        month_end = (date.today().replace(day=1) - timedelta(days=1)) if months_back == 0 else None
        cutoff = date.today() - timedelta(days=30 * months_back)
        bucket_value = 0.0
        for inv in db.scalars(select(Inventory).join(Product, Product.id == Inventory.product_id)):
            if inv.first_received_at <= cutoff and inv.quantity > 0:
                bucket_value += inv.quantity * float(inv.product.unit_cost) * 0.35
        label = (month_end or date.today()).strftime("%b") if months_back == 0 else cutoff.strftime("%b")
        capital_series.append({"label": label, "value": round(bucket_value, 2)})

    # Forecast vs actual for the last 8 weeks across all products.
    forecast_vs_actual = _forecast_vs_actual(db)

    return {
        "kpis": metrics,
        "charts": {
            "dead_stock_by_category": sorted(
                ({"category": k, "value": round(v, 2)} for k, v in dead_by_category.items()),
                key=lambda x: x["value"],
                reverse=True,
            ),
            "aging_buckets": [{"bucket": k, "count": v} for k, v in aging_buckets.items()],
            "strategy_distribution": [
                {"strategy": k, "count": v} for k, v in sorted(strategy_counts.items(), key=lambda x: -x[1])
            ],
            "capital_at_risk_series": capital_series,
            "forecast_vs_actual": forecast_vs_actual,
        },
        "generated_at": date.today().isoformat(),
    }


def _latest_forecast(db: Session, product_id, store_id) -> float:
    from app.services.demand_forecast_service import cached_forecast_30d

    return cached_forecast_30d(db, product_id, store_id)


def _forecast_vs_actual(db: Session, weeks: int = 8) -> list[dict]:
    """Compare stored 7-day forecasts against the actual units that followed them."""
    series = []
    today = date.today()
    for offset in range(weeks, 0, -1):
        window_end = today - timedelta(days=7 * (offset - 1))
        window_start = window_end - timedelta(days=7)
        actual = 0.0
        for sale in db.scalars(
            select(Sale).where(Sale.sold_on >= window_start, Sale.sold_on < window_end)
        ):
            actual += sale.quantity
        # One 7-day forecast per (product, store) — the most recent one issued on or before
        # the window start — so horizons are never double-counted.
        latest: dict[tuple, tuple[date, float]] = {}
        for row in db.scalars(select(Forecast).where(Forecast.horizon_days == 7, Forecast.as_of <= window_start)):
            key = (row.product_id, row.store_id)
            current = latest.get(key)
            if current is None or row.as_of > current[0]:
                latest[key] = (row.as_of, float(row.predicted_units))
        predicted = sum(value for _, value in latest.values())
        series.append(
            {
                "label": window_start.strftime("%d %b"),
                "forecast": round(predicted, 2),
                "actual": round(actual, 2),
            }
        )
    return series
