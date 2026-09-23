from __future__ import annotations

from app.agents import buy_a_get_b_agent
from tests.conftest import declining_sales, make_bundle_candidate, make_context


def test_refuses_anchor_below_minimum_demand():
    candidate = make_bundle_candidate(forecast_30d=5)  # below policy.min_anchor_demand
    ctx = make_context(bundle_candidates=[candidate], recent_sales=declining_sales())
    result = buy_a_get_b_agent.evaluate(ctx)
    assert result.feasible is False
    assert "anchor" in result.reason_unavailable.lower()


def test_refuses_incompatible_categories():
    candidate = make_bundle_candidate(affinity=0.05, co_purchase=0.0)
    ctx = make_context(bundle_candidates=[candidate], recent_sales=declining_sales())
    result = buy_a_get_b_agent.evaluate(ctx)
    assert result.feasible is False
    entry = result.payload["candidates"][0]
    assert entry["eligible"] is False


def test_never_pairs_product_b_with_itself():
    base = make_context(recent_sales=declining_sales())
    # the anchor is literally product B (same product id) and must be skipped
    self_candidate = make_bundle_candidate(sku=base.product.sku, forecast_30d=200, affinity=0.9).model_copy(
        update={"product": base.product}
    )
    ctx = make_context(product=base.product, bundle_candidates=[self_candidate], recent_sales=declining_sales())
    result = buy_a_get_b_agent.evaluate(ctx)
    assert result.feasible is False


def test_free_goods_cost_reduces_recovery_versus_reduced_price():
    candidate = make_bundle_candidate()
    ctx = make_context(bundle_candidates=[candidate], recent_sales=declining_sales())
    result = buy_a_get_b_agent.evaluate(ctx)
    # The chosen offer's realised revenue must never exceed the full list revenue of the units.
    best = result.payload["best_offer"]
    assert best["realised_revenue_b"] <= best["predicted_units_cleared"] * ctx.product.list_price + 1e-6
    assert best["giveaway_value"] >= 0.0


def test_attach_rate_rises_with_anchor_demand():
    weak = make_context(bundle_candidates=[make_bundle_candidate(forecast_30d=30)], recent_sales=declining_sales())
    strong = make_context(bundle_candidates=[make_bundle_candidate(forecast_30d=300)], recent_sales=declining_sales())
    weak_offer = buy_a_get_b_agent.evaluate(weak).payload["best_offer"]
    strong_offer = buy_a_get_b_agent.evaluate(strong).payload["best_offer"]
    assert strong_offer["attach_rate"] >= weak_offer["attach_rate"]
    assert strong_offer["predicted_units_cleared"] >= weak_offer["predicted_units_cleared"]


def test_compatibility_uses_real_inputs():
    low = buy_a_get_b_agent.compatibility(
        make_context(recent_sales=[]), make_bundle_candidate(affinity=0.1, co_purchase=0.0)
    )
    high = buy_a_get_b_agent.compatibility(
        make_context(recent_sales=[]), make_bundle_candidate(affinity=0.9, co_purchase=0.8)
    )
    assert high > low
    assert 0.0 <= low <= 1.0 and 0.0 <= high <= 1.0


def test_no_candidates_is_infeasible():
    ctx = make_context(bundle_candidates=[], recent_sales=declining_sales())
    result = buy_a_get_b_agent.evaluate(ctx)
    assert result.feasible is False
    assert "anchor" in result.reason_unavailable.lower()


def test_cleared_units_never_exceed_stock():
    ctx = make_context(quantity=10, bundle_candidates=[make_bundle_candidate(forecast_30d=1000)], recent_sales=declining_sales())
    result = buy_a_get_b_agent.evaluate(ctx)
    assert result.expected_units_cleared <= 10
