from __future__ import annotations

from datetime import date, timedelta

from app.schemas.domain import PolicySpec, SalePoint
from app.services import dead_stock_service as ds

TODAY = date.today()
POLICY = PolicySpec()


def _sale(days_ago: int, qty: int = 1) -> SalePoint:
    return SalePoint(sold_on=TODAY - timedelta(days=days_ago), quantity=qty, unit_price=250.0)


def test_age_days_counts_from_receipt():
    assert ds.age_days(TODAY - timedelta(days=45), TODAY) == 45
    assert ds.age_days(TODAY, TODAY) == 0
    assert ds.age_days(TODAY + timedelta(days=5), TODAY) == 0  # never negative


def test_days_since_last_sale_falls_back_to_age_when_never_sold():
    received = TODAY - timedelta(days=80)
    assert ds.days_since_last_sale(None, received, TODAY) == 80
    assert ds.days_since_last_sale(TODAY - timedelta(days=10), received, TODAY) == 10


def test_aging_trigger_fires_at_threshold_not_before():
    before = ds.detect_triggers(age=59, no_sale=0, excess_ratio=1.0, decline=0.0, history_days=100, policy=POLICY)
    at = ds.detect_triggers(age=60, no_sale=0, excess_ratio=1.0, decline=0.0, history_days=100, policy=POLICY)
    assert "aging" not in before
    assert "aging" in at


def test_no_sale_trigger_fires_at_threshold():
    assert "no_sale" in ds.detect_triggers(age=10, no_sale=30, excess_ratio=1.0, decline=0.0, history_days=100, policy=POLICY)
    assert "no_sale" not in ds.detect_triggers(age=10, no_sale=29, excess_ratio=1.0, decline=0.0, history_days=100, policy=POLICY)


def test_excess_trigger_requires_material_surplus():
    triggers = ds.detect_triggers(age=0, no_sale=0, excess_ratio=2.5, decline=0.0, history_days=100, policy=POLICY)
    assert "excess" in triggers
    triggers = ds.detect_triggers(age=0, no_sale=0, excess_ratio=2.4, decline=0.0, history_days=100, policy=POLICY)
    assert "excess" not in triggers


def test_velocity_decline_trigger_needs_history():
    assert "velocity_decline" in ds.detect_triggers(age=0, no_sale=0, excess_ratio=1.0, decline=0.6, history_days=30, policy=POLICY)
    assert "velocity_decline" not in ds.detect_triggers(age=0, no_sale=0, excess_ratio=1.0, decline=0.6, history_days=5, policy=POLICY)


def test_low_stock_fast_seller_is_not_a_recovery_candidate():
    """LOW STOCK IS NOT DEAD STOCK — the central correctness rule."""
    sales = [_sale(days_ago=d, qty=4) for d in range(1, 120, 2)]
    metrics = ds.compute_metrics(
        quantity=2,
        unit_cost=100,
        first_received_at=TODAY - timedelta(days=45),
        last_sold_at=TODAY - timedelta(days=1),
        sales=sales,
        forecast_30d=60.0,  # strong demand
        as_of=TODAY,
        policy=POLICY,
    )
    assert ds.is_low_stock(2, metrics.sales_velocity_30d) is True
    assert metrics.triggers == []
    assert ds.is_recovery_candidate(metrics, quantity=2) is False


def test_zero_quantity_is_never_a_candidate():
    metrics = ds.compute_metrics(
        quantity=0,
        unit_cost=100,
        first_received_at=TODAY - timedelta(days=200),
        last_sold_at=None,
        sales=[],
        forecast_30d=0.0,
        as_of=TODAY,
        policy=POLICY,
    )
    assert ds.is_recovery_candidate(metrics, 0) is False


def test_risk_score_is_monotonic_in_each_driver():
    base = ds.risk_score(age=10, no_sale=5, excess_ratio=1.0, decline=0.0, policy=POLICY)
    assert ds.risk_score(age=200, no_sale=5, excess_ratio=1.0, decline=0.0, policy=POLICY) > base
    assert ds.risk_score(age=10, no_sale=200, excess_ratio=1.0, decline=0.0, policy=POLICY) > base
    assert ds.risk_score(age=10, no_sale=5, excess_ratio=9.0, decline=0.0, policy=POLICY) > base
    assert ds.risk_score(age=10, no_sale=5, excess_ratio=1.0, decline=0.9, policy=POLICY) > base
    assert 0.0 <= ds.risk_score(age=9999, no_sale=9999, excess_ratio=999, decline=1.0, policy=POLICY) <= 1.0


def test_risk_bands_map_from_score():
    assert ds.risk_band(0.05) == "healthy"
    assert ds.risk_band(0.30) == "watch"
    assert ds.risk_band(0.55) == "at_risk"
    assert ds.risk_band(0.95) == "critical"


def test_capital_locked_and_at_risk_bounds():
    sales = [_sale(days_ago=d) for d in range(1, 200, 7)]
    metrics = ds.compute_metrics(
        quantity=100,
        unit_cost=50.0,
        first_received_at=TODAY - timedelta(days=150),
        last_sold_at=TODAY - timedelta(days=60),
        sales=sales,
        forecast_30d=10.0,
        as_of=TODAY,
        policy=POLICY,
    )
    assert metrics.capital_locked == 5000.0
    assert 0.0 <= metrics.capital_at_risk <= metrics.capital_locked


def test_seeded_dead_stock_sku_is_detected(seeded_db):
    """A seeded dead-stock SKU must be detected from its own data, not a flag."""
    rows = ds.dead_stock_rows(seeded_db)
    skus = {r["sku"] for r in rows}
    assert "SKU-2291" in skus
    row = next(r for r in rows if r["sku"] == "SKU-2291")
    assert row["age_days"] >= 60
    assert row["days_since_sale"] >= 30
    assert row["capital_locked"] == 120 * 100.0
    assert len(row["triggers"]) >= 1


def test_dashboard_kpis_are_aggregated_not_hardcoded(seeded_db):
    kpis = ds.dashboard_kpis(seeded_db)
    assert kpis["current_inventory_value"] > 0
    assert kpis["dead_stock_value"] > 0
    assert 0.0 <= kpis["dead_stock_pct"] <= 1.0
    assert kpis["dead_stock_units"] > 0
    assert kpis["capital_locked"] == kpis["dead_stock_value"]
    assert kpis["avg_inventory_age_days"] > 0
    # Removing all inventory must zero the KPIs — proof they are not constants.
    from app.models import Inventory

    seeded_db.query(Inventory).delete()
    seeded_db.commit()
    empty = ds.dashboard_kpis(seeded_db)
    assert empty["current_inventory_value"] == 0
    assert empty["dead_stock_value"] == 0
