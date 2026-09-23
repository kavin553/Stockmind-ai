from __future__ import annotations

import pytest

from app.agents import inter_store_swap_agent
from tests.conftest import declining_sales, make_context, make_peer


def test_rejects_destination_already_covered_by_stock():
    peer = make_peer("STR-BLR-02", quantity_on_hand=200, forecast_30d=50)
    ctx = make_context(peer_stores=[peer], recent_sales=declining_sales())
    result = inter_store_swap_agent.evaluate(ctx)
    assert result.feasible is False
    entry = result.payload["destinations"][0]
    assert entry["transfer_quantity"] == 0
    assert entry["eligible"] is False


def test_transfer_quantity_never_exceeds_excess_or_move_limit():
    peer = make_peer("STR-BLR-02", quantity_on_hand=0, forecast_30d=10000)
    ctx = make_context(quantity=120, peer_stores=[peer], recent_sales=declining_sales())
    ctx = ctx.model_copy(update={"policy": ctx.policy.model_copy(update={"transfer_max_units": 40})})
    result = inter_store_swap_agent.evaluate(ctx)
    assert result.feasible is True
    assert result.payload["best_destination"]["transfer_quantity"] == 40
    assert result.expected_units_cleared <= 40
    assert result.expected_units_cleared <= ctx.inventory.quantity


def test_rejects_when_freight_exceeds_avoided_markdown():
    # tiny quantity far away: freight swamps the recovery
    peer = make_peer("STR-HYD-01", quantity_on_hand=0, forecast_30d=6, distance_km=900)
    ctx = make_context(quantity=120, peer_stores=[peer], recent_sales=declining_sales())
    result = inter_store_swap_agent.evaluate(ctx)
    assert result.feasible is False


def test_distance_increases_transfer_cost_monotonically():
    near = make_context(peer_stores=[make_peer("STR-BLR-02", distance_km=5)], recent_sales=declining_sales())
    far = make_context(peer_stores=[make_peer("STR-BLR-02", distance_km=300)], recent_sales=declining_sales())
    near_cost = inter_store_swap_agent.transfer_cost(near, 40, 5)
    far_cost = inter_store_swap_agent.transfer_cost(far, 40, 300)
    assert far_cost > near_cost


def test_no_peer_stores_is_infeasible_not_an_exception():
    ctx = make_context(peer_stores=[], recent_sales=declining_sales())
    result = inter_store_swap_agent.evaluate(ctx)
    assert result.feasible is False
    assert "peer stores" in result.reason_unavailable


def test_best_destination_maximises_net_not_raw_recovery():
    near_weak = make_peer("STR-BLR-02", quantity_on_hand=0, forecast_30d=60, distance_km=5)
    far_strong = make_peer("STR-HYD-01", quantity_on_hand=0, forecast_30d=120, distance_km=400)
    ctx = make_context(quantity=120, peer_stores=[near_weak, far_strong], recent_sales=declining_sales())
    result = inter_store_swap_agent.evaluate(ctx)
    assert result.feasible is True
    best = result.payload["best_destination"]
    # The far store has more demand but also far more freight; whichever wins must have the
    # highest net of all eligible destinations.
    eligible = [e for e in result.payload["destinations"] if e["eligible"]]
    assert best["net_before_risk"] == max(e["net_before_risk"] for e in eligible)


def test_destination_discount_below_source_markdown_is_rejected():
    peer = make_peer("STR-BLR-02", quantity_on_hand=0, forecast_30d=200, discount=0.6)
    ctx = make_context(peer_stores=[peer], recent_sales=declining_sales())
    result = inter_store_swap_agent.evaluate(ctx)
    assert result.feasible is False


def test_zero_stock_is_infeasible():
    ctx = make_context(quantity=0, peer_stores=[make_peer("STR-BLR-02")])
    assert inter_store_swap_agent.evaluate(ctx).feasible is False
