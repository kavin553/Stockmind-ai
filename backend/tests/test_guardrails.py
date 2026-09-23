from __future__ import annotations

from app.schemas.domain import PlanAllocation, RecoveryPlanDraft
from app.services import guardrail_service
from tests.conftest import make_context


def plan_with(agent: str, units: int, net: float, detail: dict | None = None, **kwargs) -> RecoveryPlanDraft:
    allocation = PlanAllocation(
        agent=agent,
        units=units,
        expected_recovery=kwargs.pop("recovery", net + 100),
        expected_net_recovery=net,
        action_cost=kwargs.pop("action_cost", 0.0),
        detail=detail or {},
    )
    return RecoveryPlanDraft(allocations=[allocation], expected_net_recovery=net, **kwargs)


def test_clean_plan_passes():
    ctx = make_context(quantity=120)
    plan = plan_with("discount", 60, 9000, detail={"recommended_discount": 0.15})
    result = guardrail_service.evaluate(plan, ctx)
    assert result.guardrail_status == "passed"
    assert all(f.severity != "block" for f in result.guardrail_findings)


def test_discount_above_autonomous_ceiling_is_flagged_not_blocked():
    ctx = make_context(quantity=120)
    plan = plan_with("discount", 60, 9000, detail={"recommended_discount": 0.30})
    result = guardrail_service.evaluate(plan, ctx)
    assert result.guardrail_status == "flagged"
    assert any(f.code == "max_autonomous_discount" and f.severity == "flag" for f in result.guardrail_findings)
    assert guardrail_service.is_executable(result) is True


def test_b2b_price_below_floor_is_blocked():
    ctx = make_context(quantity=120)  # unit_cost 100 -> floor 80
    plan = plan_with("b2b_bulk_buyer", 60, 5000, detail={"offer_price": 40.0})
    result = guardrail_service.evaluate(plan, ctx)
    assert result.guardrail_status == "blocked"
    assert any(f.code == "b2b_price_floor" for f in result.guardrail_findings)
    assert guardrail_service.is_executable(result) is False


def test_transfer_above_limit_is_blocked():
    ctx = make_context(quantity=1000)
    plan = plan_with("inter_store_swap", 600, 4000, detail={"destination_store_id": "abc"})
    result = guardrail_service.evaluate(plan, ctx)
    assert result.guardrail_status == "blocked"
    assert any(f.code == "transfer_limit" for f in result.guardrail_findings)


def test_transfer_below_minimum_is_flagged():
    ctx = make_context(quantity=120)
    plan = plan_with("inter_store_swap", 2, 300, detail={"destination_store_id": "abc"})
    result = guardrail_service.evaluate(plan, ctx)
    assert result.guardrail_status in ("flagged", "blocked")
    assert any(f.code == "transfer_minimum" for f in result.guardrail_findings)


def test_allocating_more_than_stock_is_blocked():
    ctx = make_context(quantity=50)
    plan = plan_with("discount", 80, 9000, detail={"recommended_discount": 0.1})
    result = guardrail_service.evaluate(plan, ctx)
    assert result.guardrail_status == "blocked"
    assert any(f.code == "quantity_limit" for f in result.guardrail_findings)


def test_zero_units_is_blocked():
    ctx = make_context(quantity=50)
    plan = RecoveryPlanDraft(allocations=[PlanAllocation(agent="discount", units=0, expected_net_recovery=0)])
    result = guardrail_service.evaluate(plan, ctx)
    assert result.guardrail_status == "blocked"


def test_negative_net_recovery_is_blocked():
    ctx = make_context(quantity=50)
    plan = plan_with("discount", 20, -100, detail={"recommended_discount": 0.1})
    result = guardrail_service.evaluate(plan, ctx)
    assert result.guardrail_status == "blocked"
    assert any(f.code == "negative_net_recovery" for f in result.guardrail_findings)


def test_invalid_bundle_pairing_is_blocked():
    ctx = make_context(quantity=50)
    plan = plan_with("buy_a_get_b", 20, 2000, detail={"product_a_sku": ctx.product.sku})
    result = guardrail_service.evaluate(plan, ctx)
    assert result.guardrail_status == "blocked"
    assert any(f.code == "invalid_product_combination" for f in result.guardrail_findings)


def test_low_recovery_ratio_is_flagged():
    ctx = make_context(quantity=100)  # capital locked = 100 * 100 = 10000
    plan = plan_with("discount", 40, 500, detail={"recommended_discount": 0.1})  # 5% of capital
    result = guardrail_service.evaluate(plan, ctx)
    assert result.guardrail_status == "flagged"
    assert any(f.code == "min_recovery_ratio" and f.severity == "flag" for f in result.guardrail_findings)


def test_empty_plan_is_blocked():
    ctx = make_context(quantity=50)
    result = guardrail_service.evaluate(RecoveryPlanDraft(allocations=[]), ctx)
    assert result.guardrail_status == "blocked"
    assert any(f.code == "no_feasible_plan" for f in result.guardrail_findings)
