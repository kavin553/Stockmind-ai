from __future__ import annotations

import pytest

from app.agents import discount_agent
from tests.conftest import declining_sales, make_context, steady_sales


def test_evaluates_all_six_discount_candidates():
    ctx = make_context(recent_sales=declining_sales())
    result = discount_agent.evaluate(ctx)
    scenarios = result.payload["scenarios"]
    assert [s["discount_pct"] for s in scenarios] == [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]


def test_recommended_scenario_respects_margin_floor():
    ctx = make_context(recent_sales=declining_sales())
    result = discount_agent.evaluate(ctx)
    assert result.feasible is True
    recommended = result.payload["recommended_discount"]
    floor = ctx.product.unit_cost * (1 + ctx.policy.min_margin_pct)
    effective = ctx.product.list_price * (1 - recommended)
    assert effective >= floor


def test_scenario_economics_are_internally_consistent():
    ctx = make_context(recent_sales=declining_sales())
    result = discount_agent.evaluate(ctx)
    for scenario in result.payload["scenarios"]:
        units = scenario["predicted_units_cleared"]
        price = ctx.product.list_price * (1 - scenario["discount_pct"])
        assert abs(scenario["expected_revenue"] - units * price) < 1.0
        assert scenario["expected_recovery"] == scenario["expected_revenue"]
        assert scenario["remaining_stock"] == pytest.approx(ctx.inventory.quantity - units, abs=0.01)


def test_higher_discount_clears_at_least_as_many_units():
    ctx = make_context(recent_sales=declining_sales())
    scenarios = discount_agent.evaluate(ctx).payload["scenarios"]
    cleared = [s["predicted_units_cleared"] for s in scenarios]
    assert cleared == sorted(cleared)


def test_infeasible_when_no_stock():
    ctx = make_context(quantity=0, recent_sales=[])
    result = discount_agent.evaluate(ctx)
    assert result.feasible is False
    assert "No inventory" in result.reason_unavailable


def test_infeasible_when_price_or_cost_missing():
    product = make_context().product.model_copy(update={"list_price": 0.0})
    ctx = make_context(product=product)
    assert discount_agent.evaluate(ctx).feasible is False
    product = ctx.product.model_copy(update={"unit_cost": 0.0})
    ctx = make_context(product=product)
    assert discount_agent.evaluate(ctx).feasible is False


def test_cold_start_confidence_is_lower_than_rich_history():
    cold = make_context(recent_sales=[])
    rich = make_context(recent_sales=steady_sales(days=200, qty=2))
    cold_result = discount_agent.evaluate(cold)
    rich_result = discount_agent.evaluate(rich)
    assert cold_result.confidence < rich_result.confidence
    assert 0.0 <= cold_result.confidence <= 1.0
    assert 0.0 <= rich_result.confidence <= 1.0


def test_all_scenarios_below_floor_yields_infeasible_not_crash():
    # cost almost as high as list price -> every discount violates the margin floor
    product = make_context().product.model_copy(update={"unit_cost": 240.0, "list_price": 250.0})
    ctx = make_context(product=product, recent_sales=steady_sales())
    result = discount_agent.evaluate(ctx)
    assert result.feasible is False
    assert "margin floor" in result.reason_unavailable


def test_observed_promo_response_is_used_when_available():
    from datetime import date, timedelta

    from app.schemas.domain import SalePoint

    today = date.today()
    sales = [SalePoint(sold_on=today - timedelta(days=d), quantity=1, unit_price=250) for d in range(1, 60, 2)]
    sales += [
        SalePoint(sold_on=today - timedelta(days=d), quantity=6, unit_price=200, is_promotion=True)
        for d in range(2, 40, 3)
    ]
    ctx = make_context(recent_sales=sales)
    result = discount_agent.evaluate(ctx)
    assert result.payload["observed_response"] is not None
    assert any("promotions" in reason for reason in result.reasons)
