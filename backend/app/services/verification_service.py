"""VERIFICATION SERVICE — predicted vs simulated outcome, clearly labelled.

The "actual" side is a **prototype simulation** driven by the same seeded demand model
(category elasticity + the agent's own attach/offer mechanics) with a deterministic
pseudo-random variance keyed on the action id. It is never presented as a real-world
measurement: every row it writes carries ``label = "prototype_simulation"``.
"""
from __future__ import annotations

import hashlib
import random
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import policy
from app.models import Action, ActionResult, RecoveryPlan, VerificationResult


def _deterministic_rng(key: str) -> random.Random:
    seed = int(hashlib.sha256(key.encode()).hexdigest()[:12], 16)
    return random.Random(seed)


def simulation_factor(key: str, spread: float = 0.06) -> float:
    """Deterministic realisation factor close to 1.0 (never random across runs)."""
    rng = _deterministic_rng(key)
    return 1.0 + rng.uniform(-spread, spread)


def simulate_action(db: Session, action: Action, allocation: dict) -> dict:
    """Compare the predicted allocation against the simulated realisation and persist it."""
    predicted_units = float(allocation.get("units", 0))
    predicted_recovery = float(allocation.get("expected_recovery", 0.0))
    detail = allocation.get("detail") or {}

    # The simulation re-derives the outcome without the agents' conservative damping.
    damping = policy.simulation_elasticity_damping
    base_factor = simulation_factor(f"{action.id}:{action.agent}")
    agent_adjustment = 1.0 + (1.0 - damping) * 0.5  # un-damp the agent's caution slightly

    if action.agent == "discount":
        # Deeper discounts realise a little more clearance but a little less unit value.
        discount = float(detail.get("recommended_discount") or 0.0)
        unit_slippage = 1.0 - 0.35 * discount
        simulated_units = predicted_units * base_factor * agent_adjustment
        simulated_recovery = predicted_recovery * base_factor * unit_slippage
    elif action.agent == "inter_store_swap":
        simulated_units = predicted_units * base_factor
        simulated_recovery = predicted_recovery * base_factor * (1.0 - 0.04)  # freight slippage
    elif action.agent == "buy_a_get_b":
        simulated_units = predicted_units * base_factor * 0.97
        simulated_recovery = predicted_recovery * base_factor * 0.97
    else:  # b2b_bulk_buyer — firm quantity, small price variance only
        simulated_units = predicted_units
        simulated_recovery = predicted_recovery * base_factor

    simulated_units = round(max(0.0, min(predicted_units * 1.15, simulated_units)), 2)
    simulated_recovery = round(max(0.0, simulated_recovery), 2)
    variance = _variance(predicted_recovery, simulated_recovery)

    row = ActionResult(
        action_id=action.id,
        predicted_units=Decimal(str(round(predicted_units, 2))),
        simulated_units=Decimal(str(simulated_units)),
        predicted_recovery=Decimal(str(round(predicted_recovery, 2))),
        simulated_recovery=Decimal(str(simulated_recovery)),
        variance_pct=Decimal(str(variance)),
        label=policy.verification_label,
    )
    db.add(row)
    db.flush()
    return {
        "action_id": str(action.id),
        "agent": action.agent,
        "predicted_units": round(predicted_units, 2),
        "simulated_units": simulated_units,
        "predicted_recovery": round(predicted_recovery, 2),
        "simulated_recovery": simulated_recovery,
        "variance_pct": variance,
        "label": policy.verification_label,
    }


def _variance(predicted: float, simulated: float) -> float:
    if predicted <= 0:
        return 0.0
    return round((simulated - predicted) / predicted, 4)


def verify_plan(db: Session, plan: RecoveryPlan, executed_actions: list[dict], case) -> dict:
    rows = list(
        db.scalars(
            select(ActionResult)
            .join(Action, Action.id == ActionResult.action_id)
            .where(Action.plan_id == plan.id)
        )
    )
    predicted_units = sum(float(r.predicted_units) for r in rows)
    simulated_units = sum(float(r.simulated_units) for r in rows)
    predicted_recovery = sum(float(r.predicted_recovery) for r in rows)
    simulated_recovery = sum(float(r.simulated_recovery) for r in rows)

    verification = VerificationResult(
        plan_id=plan.id,
        predicted_units=Decimal(str(round(predicted_units, 2))),
        simulated_units=Decimal(str(round(simulated_units, 2))),
        predicted_recovery=Decimal(str(round(predicted_recovery, 2))),
        simulated_recovery=Decimal(str(round(simulated_recovery, 2))),
        units_variance_pct=Decimal(str(_variance(predicted_units, simulated_units))),
        recovery_variance_pct=Decimal(str(_variance(predicted_recovery, simulated_recovery))),
        label=policy.verification_label,
        simulated_window={"days": 30, "method": "seeded_demand_model", "actions": len(rows)},
    )
    db.add(verification)
    plan.status = "verified"
    if case is not None:
        case.status = "verified"
    db.flush()
    return {
        "predicted_units": round(predicted_units, 2),
        "simulated_units": round(simulated_units, 2),
        "predicted_recovery": round(predicted_recovery, 2),
        "simulated_recovery": round(simulated_recovery, 2),
        "units_variance_pct": _variance(predicted_units, simulated_units),
        "recovery_variance_pct": _variance(predicted_recovery, simulated_recovery),
        "label": policy.verification_label,
    }
