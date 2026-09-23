from __future__ import annotations

from app.schemas.domain import AgentResult, PlanAllocation, PolicySpec
from app.services.recovery_engine import (
    compute_net_recovery,
    select_plan,
)

POLICY = PolicySpec()


def make_result(
    agent: str,
    *,
    feasible: bool = True,
    units: float = 50,
    recovery: float = 10000,
    cost: float = 0,
    confidence: float = 0.8,
) -> AgentResult:
    return AgentResult(
        agent=agent,
        feasible=feasible,
        expected_units_cleared=units,
        expected_recovery=recovery,
        expected_loss=0.0,
        action_cost=cost,
        confidence=confidence,
    )


def test_net_recovery_subtracts_cost_friction_and_risk():
    result = make_result("discount", recovery=10000, cost=500, confidence=0.5)
    expected = 10000 - 500 - POLICY.friction_cost_ratio["discount"] * 10000 - POLICY.risk_penalty_weight * 0.5 * 10000
    assert compute_net_recovery(result, POLICY) == round(expected, 2)


def test_net_recovery_zero_for_infeasible():
    assert compute_net_recovery(make_result("discount", feasible=False), POLICY) == 0.0


def test_selects_highest_net_recovery_not_highest_raw():
    # b2b has the highest raw recovery but the largest action cost + lowest confidence.
    discount = make_result("discount", units=60, recovery=9000, cost=0, confidence=0.9)
    b2b = make_result("b2b_bulk_buyer", units=70, recovery=11000, cost=3500, confidence=0.3)
    plan = select_plan([discount, b2b], available_units=120, policy=POLICY)
    assert plan.allocations
    assert plan.allocations[0].agent == "discount"


def test_hybrid_chosen_only_when_it_strictly_beats_single():
    # Two complementary strategies each clearing half; hybrid should win.
    a = make_result("discount", units=100, recovery=12000, confidence=0.9)
    b = make_result("b2b_bulk_buyer", units=100, recovery=11900, confidence=0.9)
    plan = select_plan([a, b], available_units=200, policy=POLICY)
    single_best = max(compute_net_recovery(a, POLICY), compute_net_recovery(b, POLICY))
    if plan.strategy == "hybrid":
        assert plan.expected_net_recovery > single_best * (1 + POLICY.hybrid_min_improvement)
        assert sum(x.units for x in plan.allocations) <= 200
    else:
        assert plan.expected_net_recovery >= single_best


def test_no_strategy_can_allocate_units_another_already_allocated():
    results = [
        make_result("discount", units=100, recovery=15000),
        make_result("inter_store_swap", units=100, recovery=16000, cost=800),
        make_result("b2b_bulk_buyer", units=100, recovery=14000),
    ]
    plan = select_plan(results, available_units=100, policy=POLICY)
    total = sum(a.units for a in plan.allocations)
    assert total <= 100
    assert all(a.units >= 0 for a in plan.allocations)
    # no duplicate agent
    agents = [a.agent for a in plan.allocations]
    assert len(agents) == len(set(agents))


def test_hybrid_allocation_never_exceeds_available_units():
    results = [
        make_result("discount", units=500, recovery=50000),
        make_result("buy_a_get_b", units=500, recovery=52000),
        make_result("b2b_bulk_buyer", units=500, recovery=48000, cost=2000),
    ]
    plan = select_plan(results, available_units=200, policy=POLICY)
    assert sum(a.units for a in plan.allocations) <= 200


def test_infeasible_agents_do_not_break_selection():
    results = [
        make_result("discount", feasible=False, recovery=0, units=0),
        make_result("inter_store_swap", feasible=False, recovery=0, units=0),
        make_result("buy_a_get_b", feasible=False, recovery=0, units=0),
        make_result("b2b_bulk_buyer", feasible=True, units=40, recovery=8000, confidence=0.7),
    ]
    plan = select_plan(results, available_units=120, policy=POLICY)
    assert plan.allocations
    assert plan.allocations[0].agent == "b2b_bulk_buyer"


def test_negative_net_recovery_never_selected():
    # recovery smaller than the action cost produces a negative net
    loss_maker = make_result("inter_store_swap", units=50, recovery=100, cost=9000, confidence=0.5)
    plan = select_plan([loss_maker], available_units=120, policy=POLICY)
    assert plan.allocations == []
    assert "No acceptable recovery path" in plan.explanation


def test_no_feasible_plan_returns_empty_with_explanation():
    plan = select_plan([], available_units=100, policy=POLICY)
    assert plan.allocations == []
    assert plan.expected_net_recovery == 0.0
    assert plan.explanation


def test_zero_available_units_yields_no_plan():
    plan = select_plan([make_result("discount")], available_units=0, policy=POLICY)
    assert plan.allocations == []


def test_plan_confidence_is_unit_weighted():
    from app.services.recovery_engine import _plan_from_allocations

    draft = _plan_from_allocations(
        "hybrid",
        [
            PlanAllocation(agent="discount", units=10, expected_recovery=100, expected_net_recovery=90, confidence=0.9),
            PlanAllocation(agent="b2b_bulk_buyer", units=30, expected_recovery=100, expected_net_recovery=80, confidence=0.5),
        ],
        POLICY,
    )
    assert draft.confidence == round((0.9 * 10 + 0.5 * 30) / 40, 4)
    assert draft.expected_net_recovery == 170.0
