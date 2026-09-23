from __future__ import annotations

from app.agents import b2b_bulk_buyer_agent
from tests.conftest import declining_sales, make_buyer, make_context


def test_rejects_buyers_without_category_match():
    buyer = make_buyer(categories=["Furniture"])
    ctx = make_context(b2b_buyers=[buyer], recent_sales=declining_sales())
    result = b2b_bulk_buyer_agent.evaluate(ctx)
    assert result.feasible is False
    assert result.payload["buyers"][0]["eligible"] is False


def test_offer_never_below_cost_floor():
    # preferred price below the floor -> buyer rejected rather than undercutting cost
    buyer = make_buyer(preferred_price=10.0)
    ctx = make_context(b2b_buyers=[buyer], recent_sales=declining_sales())
    result = b2b_bulk_buyer_agent.evaluate(ctx)
    assert result.feasible is False
    assert "floor" in result.payload["buyers"][0]["reason"]


def test_offer_price_respects_floor_when_feasible():
    buyer = make_buyer(preferred_price=180.0)
    ctx = make_context(b2b_buyers=[buyer], recent_sales=declining_sales())
    result = b2b_bulk_buyer_agent.evaluate(ctx)
    assert result.feasible is True
    floor = ctx.product.unit_cost * ctx.policy.b2b_price_floor_pct
    assert result.payload["best_buyer"]["offer_price"] >= floor


def test_respects_buyer_minimum_quantity():
    buyer = make_buyer(required_quantity=500, preferred_price=180.0)
    ctx = make_context(b2b_buyers=[buyer], quantity=120, recent_sales=declining_sales())
    result = b2b_bulk_buyer_agent.evaluate(ctx)
    assert result.feasible is False


def test_respects_buyer_budget():
    buyer = make_buyer(required_quantity=10, budget=1000, preferred_price=180.0)
    ctx = make_context(b2b_buyers=[buyer], quantity=120, recent_sales=declining_sales())
    result = b2b_bulk_buyer_agent.evaluate(ctx)
    if result.feasible:
        assert result.expected_recovery <= 1000 + 1e-6
    else:
        assert "budget" in result.payload["buyers"][0]["reason"]


def test_proximity_reduces_score_for_distant_buyers():
    near = b2b_bulk_buyer_agent.score_buyer(make_context(), make_buyer(), distance_km=10)
    far = b2b_bulk_buyer_agent.score_buyer(make_context(), make_buyer(), distance_km=900)
    assert far["match_score"] < near["match_score"]


def test_best_buyer_maximises_recovery():
    small = make_buyer("Small Co", required_quantity=40, budget=20000, preferred_price=170.0)
    large = make_buyer("Large Co", required_quantity=100, budget=500000, preferred_price=180.0)
    ctx = make_context(b2b_buyers=[small, large], quantity=150, recent_sales=declining_sales())
    result = b2b_bulk_buyer_agent.evaluate(ctx)
    assert result.feasible is True
    eligible = [e for e in result.payload["buyers"] if e.get("eligible")]
    assert result.payload["best_buyer"]["expected_recovery"] == max(e["expected_recovery"] for e in eligible)


def test_no_buyers_is_infeasible():
    ctx = make_context(b2b_buyers=[], recent_sales=declining_sales())
    result = b2b_bulk_buyer_agent.evaluate(ctx)
    assert result.feasible is False


def test_zero_stock_is_infeasible():
    ctx = make_context(quantity=0, b2b_buyers=[make_buyer()])
    assert b2b_bulk_buyer_agent.evaluate(ctx).feasible is False


def test_haversine_is_symmetric_and_zero_at_same_point():
    assert b2b_bulk_buyer_agent.haversine_km(12.97, 77.64, 12.97, 77.64) == 0.0
    assert abs(
        b2b_bulk_buyer_agent.haversine_km(12.97, 77.64, 17.44, 78.35)
        - b2b_bulk_buyer_agent.haversine_km(17.44, 78.35, 12.97, 77.64)
    ) < 1e-6
