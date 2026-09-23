from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models import Action, ActionResult, RecoveryPlan, VerificationResult
from app.services.verification_service import _variance, simulation_factor


def test_variance_formula():
    assert _variance(100, 110) == 0.1
    assert _variance(100, 90) == -0.1


def test_variance_does_not_divide_by_zero():
    assert _variance(0, 50) == 0.0
    assert _variance(0, 0) == 0.0


def test_simulation_factor_is_deterministic_across_runs():
    assert simulation_factor("action-1") == simulation_factor("action-1")
    assert simulation_factor("action-1") != simulation_factor("action-2")
    for key in ("a", "b", "c", "d", "e"):
        assert 0.9 <= simulation_factor(key, spread=0.06) <= 1.1


def test_action_result_rows_are_labelled_prototype_simulation(seeded_db):
    """Executing a plan must stamp every simulated outcome as a prototype simulation."""
    from app.models import Inventory, Product, Store, RecoveryCase
    from app.services import recovery_engine

    session = seeded_db
    product = session.scalars(select(Product).where(Product.sku == "SKU-2291")).one()
    store = session.scalars(select(Store).where(Store.code == "STR-BLR-01")).one()
    case, ctx, results, plan, draft = recovery_engine.analyze(session, product.id, store.id)
    session.commit()

    if plan.guardrail_status == "blocked" or not plan.allocations:
        return  # nothing to verify for this fixture

    from app.services import execution_service

    execution_service.execute_plan(session, plan, actor="test")

    rows = list(session.scalars(select(ActionResult)))
    assert rows, "execution should have produced action results"
    assert all(r.label == "prototype_simulation" for r in rows)

    verification = session.scalars(select(VerificationResult).where(VerificationResult.plan_id == plan.id)).first()
    assert verification is not None
    assert verification.label == "prototype_simulation"
    assert verification.simulated_window["method"] == "seeded_demand_model"
    assert float(verification.predicted_recovery) >= 0.0
