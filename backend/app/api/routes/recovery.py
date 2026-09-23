from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, parse_uuid
from app.agents import AGENT_LABELS
from app.models import (
    Action,
    ActionResult,
    AgentResult,
    AuditLog,
    Inventory,
    Product,
    RecoveryCase,
    RecoveryPlan,
    Store,
    User,
    VerificationResult,
)
from app.services import audit_service, dead_stock_service, execution_service, guardrail_service, recovery_engine

router = APIRouter(prefix="/recovery", tags=["recovery"])


class AnalyzeRequest(BaseModel):
    product_id: str
    store_id: str | None = None
    store_code: str | None = None


class ExecuteRequest(BaseModel):
    plan_id: str
    idempotency_key: str | None = None


class DemoRunRequest(BaseModel):
    scenario: str | None = None


def _serialize_plan(plan: RecoveryPlan) -> dict:
    return {
        "id": str(plan.id),
        "case_id": str(plan.case_id),
        "strategy": plan.strategy,
        "allocations": plan.allocations,
        "expected_recovery": float(plan.expected_recovery),
        "expected_loss": float(plan.expected_loss),
        "total_action_cost": float(plan.total_action_cost),
        "expected_net_recovery": float(plan.expected_net_recovery),
        "confidence": float(plan.confidence),
        "guardrail_status": plan.guardrail_status,
        "guardrail_findings": plan.guardrail_findings,
        "explanation": plan.explanation,
        "status": plan.status,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
    }


def _serialize_agent(row: AgentResult) -> dict:
    return {
        "agent": row.agent,
        "label": AGENT_LABELS.get(row.agent, row.agent),
        "feasible": row.feasible,
        "reason_unavailable": row.reason_unavailable,
        "expected_units_cleared": float(row.expected_units_cleared),
        "expected_recovery": float(row.expected_recovery),
        "expected_loss": float(row.expected_loss),
        "action_cost": float(row.action_cost),
        "expected_net_recovery": float(row.expected_net_recovery),
        "confidence": float(row.confidence),
        "reasons": row.reasons,
        "payload": row.payload,
    }


@router.post("/analyze")
def analyze(payload: AnalyzeRequest, db: Session = Depends(db_session), user: User = Depends(current_user)) -> dict:
    product_id = parse_uuid(payload.product_id, "product id")
    store_id = _resolve_store(db, payload.store_id, payload.store_code)
    try:
        case, ctx, results, plan, draft = recovery_engine.analyze(db, product_id, store_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    audit_service.record(
        db,
        actor=user.email,
        actor_type="user",
        sku=ctx.product.sku,
        trigger=",".join(ctx.metrics.triggers) or "manual",
        decision="analyzed",
        inputs_summary={
            "store": ctx.store.code,
            "quantity": ctx.inventory.quantity,
            "age_days": ctx.metrics.age_days,
            "forecast_30d": ctx.forecast.forecast_30d,
        },
        recommendation={"strategy": draft.strategy, "guardrail_status": draft.guardrail_status},
        confidence=draft.confidence,
    )
    db.commit()
    return {
        "case": _serialize_case(case),
        "metrics": ctx.metrics.model_dump(),
        "forecast": ctx.forecast.model_dump(mode="json"),
        "agent_results": [_serialize_agent(r) for r in results],
        "plan": _serialize_plan(plan),
    }


@router.post("/execute")
def execute(payload: ExecuteRequest, db: Session = Depends(db_session), user: User = Depends(current_user)) -> dict:
    plan_id = parse_uuid(payload.plan_id, "plan id")
    plan = db.get(RecoveryPlan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found.")
    if plan.status in ("executed", "verified") and not payload.idempotency_key:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This plan has already been executed. Provide a new idempotency_key to replay it explicitly.",
        )
    case = db.get(RecoveryCase, plan.case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recovery case not found.")

    # Guardrails re-run against current stock before anything moves.
    product = db.get(Product, case.product_id)
    store = db.get(Store, case.store_id)
    inventory = db.scalars(
        select(Inventory).where(Inventory.product_id == case.product_id, Inventory.store_id == case.store_id)
    ).first()
    if inventory is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Inventory row no longer exists.")
    ctx = recovery_engine.build_context(db, product, store, inventory)
    from app.schemas.domain import PlanAllocation, RecoveryPlanDraft

    draft = RecoveryPlanDraft(
        strategy=plan.strategy,
        allocations=[PlanAllocation(**{**a, "units": int(a["units"])}) for a in (plan.allocations or [])],
        expected_recovery=float(plan.expected_recovery),
        total_action_cost=float(plan.total_action_cost),
        expected_net_recovery=float(plan.expected_net_recovery),
        confidence=float(plan.confidence),
    )
    draft = guardrail_service.evaluate(draft, ctx)
    plan.guardrail_status = draft.guardrail_status
    plan.guardrail_findings = [f.model_dump(mode="json") for f in draft.guardrail_findings]
    if not guardrail_service.is_executable(draft):
        db.commit()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": "Guardrails blocked this plan.", "findings": plan.guardrail_findings},
        )

    try:
        outcome = execution_service.execute_plan(
            db, plan, actor=user.email, idempotency_prefix=payload.idempotency_key
        )
    except execution_service.ExecutionError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return outcome


@router.get("/history")
def history(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(db_session),
    _: User = Depends(current_user),
) -> dict:
    stmt = (
        select(Action, RecoveryPlan, RecoveryCase, Product, Store)
        .join(RecoveryPlan, RecoveryPlan.id == Action.plan_id)
        .join(RecoveryCase, RecoveryCase.id == Action.case_id)
        .join(Product, Product.id == RecoveryCase.product_id)
        .join(Store, Store.id == RecoveryCase.store_id)
        .order_by(Action.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(Action.status == status_filter)
    rows = db.execute(stmt).all()
    items = []
    for action, plan, case, product, store in rows:
        result = db.scalars(select(ActionResult).where(ActionResult.action_id == action.id)).first()
        verification = db.scalars(
            select(VerificationResult).where(VerificationResult.plan_id == plan.id)
        ).first()
        items.append(
            {
                "action_id": str(action.id),
                "plan_id": str(plan.id),
                "case_id": str(case.id),
                "sku": product.sku,
                "name": product.name,
                "store": store.code,
                "agent": action.agent,
                "label": AGENT_LABELS.get(action.agent, action.agent),
                "units": action.units,
                "status": action.status,
                "executed_at": action.executed_at.isoformat() if action.executed_at else None,
                "result_summary": action.result_summary,
                "guardrail_status": plan.guardrail_status,
                "expected_net_recovery": float(plan.expected_net_recovery),
                "verification": (
                    {
                        "predicted_units": float(verification.predicted_units),
                        "simulated_units": float(verification.simulated_units),
                        "predicted_recovery": float(verification.predicted_recovery),
                        "simulated_recovery": float(verification.simulated_recovery),
                        "units_variance_pct": float(verification.units_variance_pct),
                        "recovery_variance_pct": float(verification.recovery_variance_pct),
                        "label": verification.label,
                    }
                    if verification
                    else (result and {
                        "predicted_units": float(result.predicted_units),
                        "simulated_units": float(result.simulated_units),
                        "predicted_recovery": float(result.predicted_recovery),
                        "simulated_recovery": float(result.simulated_recovery),
                        "variance_pct": float(result.variance_pct),
                        "label": result.label,
                    })
                ),
            }
        )
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start : start + page_size], "total": total, "page": page, "page_size": page_size}


@router.get("/{plan_id}")
def plan_detail(plan_id: str, db: Session = Depends(db_session), _: User = Depends(current_user)) -> dict:
    plan = db.get(RecoveryPlan, parse_uuid(plan_id, "plan id"))
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found.")
    case = db.get(RecoveryCase, plan.case_id)
    return {
        "plan": _serialize_plan(plan),
        "case": _serialize_case(case) if case else None,
        "agent_results": [
            _serialize_agent(r)
            for r in db.scalars(select(AgentResult).where(AgentResult.case_id == plan.case_id))
        ],
        "timeline": build_timeline(db, case, plan),
    }


@router.get("/{plan_id}/timeline")
def timeline(plan_id: str, db: Session = Depends(db_session), _: User = Depends(current_user)) -> dict:
    plan = db.get(RecoveryPlan, parse_uuid(plan_id, "plan id"))
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found.")
    case = db.get(RecoveryCase, plan.case_id)
    return {"events": build_timeline(db, case, plan)}


@router.post("/demo-run")
def demo_run(payload: DemoRunRequest, db: Session = Depends(db_session), user: User = Depends(current_user)) -> dict:
    """Deterministic autonomous recovery: detect → evaluate → guardrail → execute → verify."""
    candidates = dead_stock_service.dead_stock_rows(db, limit=200)
    if not candidates:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No dead-stock candidates exist to run the demo on.")

    chosen = None
    plan = None
    results = None
    ctx = None
    case = None
    for candidate in candidates:
        product_id = uuid.UUID(candidate["product_id"])
        store_id = uuid.UUID(candidate["store_id"])
        try:
            case, ctx, results, plan, draft = recovery_engine.analyze(db, product_id, store_id)
        except ValueError:
            continue
        if draft.guardrail_status != "blocked" and draft.allocations:
            chosen = candidate
            audit_service.record(
                db,
                actor=user.email,
                actor_type="user",
                sku=ctx.product.sku,
                trigger="autonomous_demo",
                decision="case_detected",
                inputs_summary={"quantity": ctx.inventory.quantity, "age_days": ctx.metrics.age_days},
                recommendation={"triggers": ctx.metrics.triggers},
                confidence=ctx.forecast.confidence,
            )
            db.commit()
            break
        db.rollback()

    if chosen is None or plan is None or ctx is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Every candidate was blocked by guardrails; no autonomous run is possible right now.",
        )

    outcome = execution_service.execute_plan(db, plan, actor=user.email, idempotency_prefix="demo-run")
    return {
        "scenario": payload.scenario or "highest_priority_candidate",
        "case": _serialize_case(case),
        "product": {"sku": ctx.product.sku, "name": ctx.product.name},
        "store": ctx.store.code,
        "metrics": ctx.metrics.model_dump(),
        "forecast": ctx.forecast.model_dump(mode="json"),
        "agent_results": [_serialize_agent(r) for r in results],
        "plan": _serialize_plan(plan),
        "execution": outcome,
        "timeline": build_timeline(db, case, plan),
    }


def build_timeline(db: Session, case: RecoveryCase | None, plan: RecoveryPlan | None) -> list[dict]:
    """Timeline assembled from real stored timestamps — never fabricated."""
    events: list[dict] = []
    if case is None:
        return events

    def stamp(dt) -> str:
        return dt.isoformat() if dt else ""

    product = db.get(Product, case.product_id)
    events.append(
        {
            "at": stamp(case.detected_at),
            "event": "case_detected",
            "message": f"Dead-stock case detected for {product.sku} at {ctx_store(db, case)}: triggers {', '.join(case.triggers or []) or 'manual'}.",
            "detail": {"age_days": case.age_days, "days_since_sale": case.days_since_sale, "risk_band": case.risk_band},
        }
    )
    for row in db.scalars(
        select(AgentResult).where(AgentResult.case_id == case.id).order_by(AgentResult.created_at, AgentResult.agent)
    ):
        events.append(
            {
                "at": stamp(row.created_at),
                "event": f"agent_{row.agent}",
                "message": (
                    f"{AGENT_LABELS.get(row.agent)} "
                    + (
                        f"evaluated the opportunity: {float(row.expected_units_cleared):.0f} units, "
                        f"expected net recovery {float(row.expected_net_recovery):,.0f}."
                        if row.feasible
                        else f"reported not feasible — {row.reason_unavailable}"
                    )
                ),
                "detail": {"confidence": float(row.confidence), "feasible": row.feasible},
            }
        )
    if plan is not None:
        events.append(
            {
                "at": stamp(plan.created_at),
                "event": "plan_selected",
                "message": plan.explanation or "Recovery engine selected a plan.",
                "detail": {
                    "strategy": plan.strategy,
                    "expected_net_recovery": float(plan.expected_net_recovery),
                    "guardrail_status": plan.guardrail_status,
                },
            }
        )
        for finding in plan.guardrail_findings or []:
            events.append(
                {
                    "at": stamp(plan.created_at),
                    "event": "guardrail",
                    "message": finding.get("message", ""),
                    "detail": {"severity": finding.get("severity"), "code": finding.get("code")},
                }
            )
        for action in db.scalars(select(Action).where(Action.plan_id == plan.id).order_by(Action.created_at)):
            events.append(
                {
                    "at": stamp(action.executed_at or action.created_at),
                    "event": "action_executed",
                    "message": (
                        f"{AGENT_LABELS.get(action.agent)} executed for {action.units} units "
                        f"({action.status})."
                    ),
                    "detail": action.result_summary,
                }
            )
    for entry in db.scalars(
        select(AuditLog).where(AuditLog.sku == product.sku).order_by(AuditLog.occurred_at, AuditLog.id)
    ):
        if entry.decision in ("executed", "analyzed", "case_detected"):
            events.append(
                {
                    "at": stamp(entry.occurred_at),
                    "event": f"audit_{entry.decision}",
                    "message": f"Audit recorded: {entry.decision} by {entry.actor}.",
                    "detail": entry.execution_result or {},
                }
            )
    events.sort(key=lambda e: (e["at"], e["event"]))
    return events


def ctx_store(db: Session, case: RecoveryCase) -> str:
    store = db.get(Store, case.store_id)
    return store.code if store else "unknown store"


def _serialize_case(case: RecoveryCase) -> dict:
    return {
        "id": str(case.id),
        "product_id": str(case.product_id),
        "store_id": str(case.store_id),
        "status": case.status,
        "triggers": case.triggers,
        "age_days": case.age_days,
        "days_since_sale": case.days_since_sale,
        "forecast_30d": float(case.forecast_30d),
        "excess_units": float(case.excess_units),
        "stock_units": case.stock_units,
        "capital_locked": float(case.capital_locked),
        "capital_at_risk": float(case.capital_at_risk),
        "risk_score": float(case.risk_score),
        "risk_band": case.risk_band,
        "detected_at": case.detected_at.isoformat() if case.detected_at else None,
    }


def _resolve_store(db: Session, store_id: str | None, store_code: str | None) -> uuid.UUID:
    if store_id:
        return parse_uuid(store_id, "store id")
    if store_code:
        store = db.scalars(select(Store).where(Store.code == store_code)).first()
        if store is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown store '{store_code}'.")
        return store.id
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide store_id or store_code.")
