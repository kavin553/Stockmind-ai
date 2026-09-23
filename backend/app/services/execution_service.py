"""EXECUTION SERVICE (simulated execution — writes real state to the database).

No payment/POS/marketplace integration is called. Every strategy mutates actual rows inside
one transaction and produces a ``prototype_simulation`` ActionResult, so the dashboard after
execution reflects genuine database state rather than an animation.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    B2BOrder,
    Inventory,
    Promotion,
    RecoveryCase,
    RecoveryPlan,
    StoreTransfer,
    Action,
)
from app.services import audit_service, verification_service


class ExecutionError(RuntimeError):
    pass


def _inventory(db: Session, product_id: uuid.UUID, store_id: uuid.UUID) -> Inventory:
    row = db.scalars(
        select(Inventory).where(Inventory.product_id == product_id, Inventory.store_id == store_id)
    ).first()
    if row is None:
        raise ExecutionError("Inventory row missing for the allocation's product and store.")
    return row


def _snapshot(db: Session, case: RecoveryCase) -> dict:
    inv = _inventory(db, case.product_id, case.store_id)
    return {
        "quantity": inv.quantity,
        "discount_pct": float(inv.discount_pct),
        "capital_locked": round(inv.quantity * float(inv.product.unit_cost), 2),
    }


def execute_plan(
    db: Session,
    plan: RecoveryPlan,
    *,
    actor: str = "system",
    idempotency_prefix: str | None = None,
) -> dict:
    """Execute every allocation of a plan. Safe to call twice with the same prefix."""
    if plan.guardrail_status == "blocked":
        raise ExecutionError("This plan is blocked by guardrails and cannot be executed.")

    case: RecoveryCase = db.get(RecoveryCase, plan.case_id)
    if case is None:
        raise ExecutionError("Plan references a missing recovery case.")

    prefix = idempotency_prefix or f"plan-{plan.id}"
    before = _snapshot(db, case)
    allocations = list(plan.allocations or [])
    if not allocations:
        raise ExecutionError("Plan has no allocations to execute.")

    executable = [a for a in allocations if int(a.get("units", 0)) > 0]
    total_units = sum(int(a["units"]) for a in executable)
    inventory = _inventory(db, case.product_id, case.store_id)
    if total_units > inventory.quantity:
        raise ExecutionError(
            f"Plan allocates {total_units} units but only {inventory.quantity} remain in stock."
        )

    executed_actions: list[dict] = []
    action_results: list[dict] = []

    for index, allocation in enumerate(executable):
        agent = allocation["agent"]
        units = int(allocation["units"])
        key = f"{prefix}:{agent}:{index}"
        existing = db.scalars(select(Action).where(Action.idempotency_key == key)).first()
        if existing is not None:
            executed_actions.append({"id": str(existing.id), "agent": agent, "units": units, "status": existing.status, "replayed": True})
            continue

        action = Action(
            plan_id=plan.id,
            case_id=case.id,
            agent=agent,
            units=units,
            status="pending",
            idempotency_key=key,
        )
        db.add(action)
        db.flush()

        detail = allocation.get("detail") or {}
        # Re-read inside the loop: an earlier allocation may already have moved stock.
        inventory = _inventory(db, case.product_id, case.store_id)
        units = min(units, inventory.quantity)
        summary: dict = {"agent": agent, "units": units}

        if agent == "discount":
            discount = float(detail.get("recommended_discount") or 0.0)
            inventory.discount_pct = Decimal(str(round(discount, 4)))
            inventory.quantity -= units
            db.add(
                Promotion(
                    kind="discount",
                    product_id=case.product_id,
                    store_id=case.store_id,
                    discount_pct=Decimal(str(round(discount, 4))),
                    incentive="price_cut",
                    starts_on=date.today(),
                    ends_on=date.today() + timedelta(days=30),
                    created_by_action_id=action.id,
                )
            )
            summary.update({"discount_pct": discount, "remaining_stock": inventory.quantity})

        elif agent == "inter_store_swap":
            destination_id = detail.get("destination_store_id")
            if not destination_id:
                action.status = "failed"
                summary["error"] = "missing destination"
            else:
                destination = _inventory(db, case.product_id, uuid.UUID(str(destination_id)))
                inventory.quantity -= units
                destination.quantity += units
                transfer = StoreTransfer(
                    product_id=case.product_id,
                    source_store_id=case.store_id,
                    destination_store_id=destination.store_id,
                    quantity=units,
                    transfer_cost=Decimal(str(allocation.get("action_cost", 0))),
                    status="completed",
                    created_by_action_id=action.id,
                )
                db.add(transfer)
                summary.update(
                    {
                        "destination_store_id": str(destination.store_id),
                        "destination_quantity": destination.quantity,
                        "remaining_stock": inventory.quantity,
                    }
                )

        elif agent == "buy_a_get_b":
            anchor_sku = detail.get("product_a_sku")
            anchor_id = _anchor_product_id(db, anchor_sku)
            if anchor_id is None:
                action.status = "failed"
                summary["error"] = "anchor product not found"
            else:
                inventory.quantity -= units
                db.add(
                    Promotion(
                        kind="buy_a_get_b",
                        product_id=case.product_id,
                        anchor_product_id=anchor_id,
                        store_id=case.store_id,
                        incentive="bundle",
                        bundle_type=detail.get("bundle_type"),
                        starts_on=date.today(),
                        ends_on=date.today() + timedelta(days=30),
                        created_by_action_id=action.id,
                    )
                )
                summary.update({"anchor_sku": anchor_sku, "bundle_type": detail.get("bundle_type"), "remaining_stock": inventory.quantity})

        elif agent == "b2b_bulk_buyer":
            offer = float(detail.get("offer_price") or 0.0)
            inventory.quantity -= units
            db.add(
                B2BOrder(
                    buyer_id=_buyer_id_for_plan(db, plan),
                    product_id=case.product_id,
                    store_id=case.store_id,
                    quantity=units,
                    unit_price=Decimal(str(round(offer, 2))),
                    total_value=Decimal(str(round(offer * units, 2))),
                    status="confirmed",
                    created_by_action_id=action.id,
                )
            )
            summary.update({"offer_price": offer, "order_value": round(offer * units, 2), "remaining_stock": inventory.quantity})
        else:
            action.status = "skipped"
            summary["error"] = f"unknown agent '{agent}'"

        if inventory.quantity < 0:  # defensive: never allow negative stock
            raise ExecutionError("Execution would drive inventory negative — aborted.")

        inventory.updated_at = date.today()
        if action.status == "pending":
            action.status = "executed"
            action.executed_at = audit_service.utcnow()
        action.result_summary = summary
        db.flush()

        result = verification_service.simulate_action(db, action, allocation)
        action_results.append(result)
        executed_actions.append({"id": str(action.id), "agent": agent, "units": units, "status": action.status})

    plan.status = "executed"
    case.status = "executed"
    db.flush()
    after = _snapshot(db, case)

    audit_service.record(
        db,
        actor=actor,
        actor_type="user" if actor != "system" else "system",
        sku=inventory.product.sku,
        trigger=",".join(case.triggers or []) or "manual",
        agent=",".join(sorted({a["agent"] for a in executed_actions})),
        decision="executed",
        inputs_summary={"plan_id": str(plan.id), "strategy": plan.strategy, "allocations": allocations},
        recommendation={"expected_net_recovery": float(plan.expected_net_recovery)},
        confidence=float(plan.confidence),
        execution_result={"before": before, "after": after, "actions": executed_actions},
    )

    verification = verification_service.verify_plan(db, plan, executed_actions, case)

    db.commit()
    return {
        "plan_id": str(plan.id),
        "case_id": str(case.id),
        "actions": executed_actions,
        "action_results": action_results,
        "before": before,
        "after": after,
        "units_cleared": before["quantity"] - after["quantity"],
        "verification": verification,
    }


def _anchor_product_id(db: Session, sku: str | None) -> uuid.UUID | None:
    if not sku:
        return None
    from app.models import Product

    product = db.scalars(select(Product).where(Product.sku == sku)).first()
    return product.id if product else None


def _buyer_id_for_plan(db: Session, plan: RecoveryPlan) -> uuid.UUID:
    """Resolve the buyer the plan actually used, falling back to the first active buyer."""
    from app.models import B2BBuyer

    for allocation in plan.allocations or []:
        name = (allocation.get("detail") or {}).get("buyer_name")
        if name:
            buyer = db.scalars(select(B2BBuyer).where(B2BBuyer.business_name == name)).first()
            if buyer:
                return buyer.id
    buyer = db.scalars(select(B2BBuyer).where(B2BBuyer.is_active.is_(True))).first()
    if buyer is None:
        raise ExecutionError("No B2B buyer is available to place the order.")
    return buyer.id
