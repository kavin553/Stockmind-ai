"""RECOVERY DECISION ENGINE (orchestration service — explicitly **not** a fifth AI agent).

Responsibilities
----------------
1. assemble a :class:`RecoveryContext` from the database,
2. run the four agents (crash-isolated),
3. normalise every result onto one metric — **expected net recovery**,
4. choose the best single strategy *or* a hybrid split that does not double-count inventory,
5. persist the case, the agent results and the plan.

Pure helpers (:func:`compute_net_recovery`, :func:`select_plan`) are unit-tested without a
database.
"""
from __future__ import annotations

import itertools
import uuid
from datetime import date, timedelta
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AGENT_REGISTRY
from app.config import policy as default_policy
from app.models import (
    AgentResult as AgentResultRow,
    B2BBuyer,
    Category,
    Forecast,
    Inventory,
    Product,
    Promotion,
    RecoveryCase,
    RecoveryPlan,
    Sale,
    Store,
)
from app.schemas.domain import (
    AgentResult,
    BundleCandidate,
    BuyerSpec,
    PlanAllocation,
    PolicySpec,
    ProductSpec,
    RecoveryContext,
    RecoveryPlanDraft,
    SalePoint,
    StoreDemand,
    StoreSpec,
)
from app.services import dead_stock_service, demand_forecast_service


# --------------------------------------------------------------------------- pure scoring


def compute_net_recovery(result: AgentResult, policy: PolicySpec | None = None) -> float:
    """Expected net recovery = recovery − action cost − friction − risk penalty.

    Promotional give-aways are already excluded from ``expected_recovery`` by each agent
    (they are foregone revenue, not cash cost), so they are not subtracted twice here.
    """
    p = policy or PolicySpec()
    if not result.feasible:
        return 0.0
    recovery = max(0.0, float(result.expected_recovery))
    friction = p.friction_cost_ratio.get(result.agent, 0.02) * recovery
    risk = p.risk_penalty_weight * (1.0 - float(result.confidence)) * recovery
    net = recovery - float(result.action_cost) - friction - risk
    return round(net, 2)


def per_unit(result: AgentResult) -> float:
    units = float(result.expected_units_cleared)
    return float(result.expected_recovery) / units if units > 0 else 0.0


def _scale(result: AgentResult, units: int, policy: PolicySpec) -> PlanAllocation:
    """Pro-rate an agent's economics onto a partial unit allocation."""
    available = float(result.expected_units_cleared)
    factor = (units / available) if available > 0 else 0.0
    recovery = round(float(result.expected_recovery) * factor, 2)
    cost = round(float(result.action_cost) * factor, 2)
    friction = round(policy.friction_cost_ratio.get(result.agent, 0.02) * recovery, 2)
    risk = round(policy.risk_penalty_weight * (1.0 - float(result.confidence)) * recovery, 2)
    net = round(recovery - cost - friction - risk, 2)
    return PlanAllocation(
        agent=result.agent,
        units=int(units),
        expected_recovery=recovery,
        expected_net_recovery=net,
        action_cost=cost,
        confidence=float(result.confidence),
        detail={
            "friction_cost": friction,
            "risk_penalty": risk,
            "per_unit_recovery": round(per_unit(result), 2),
            "confidence": float(result.confidence),
            # Hints the guardrail layer needs, carried through from the agent payload.
            "recommended_discount": result.payload.get("recommended_discount"),
            "offer_price": (result.payload.get("best_buyer") or {}).get("offer_price"),
            "bundle_type": (result.payload.get("best_offer") or {}).get("bundle_type"),
            "product_a_sku": (result.payload.get("best_offer") or {}).get("product_a_sku"),
            "destination_store_id": (result.payload.get("best_destination") or {}).get(
                "destination_store_id"
            ),
            "buyer_name": (result.payload.get("best_buyer") or {}).get("buyer_name"),
        },
    )


def _weights(strategies: int, steps: list[float]) -> list[tuple[float, ...]]:
    combos = []
    for combo in itertools.product(steps, repeat=strategies):
        if abs(sum(combo) - 1.0) < 1e-9:
            combos.append(combo)
    return combos


def _candidate_allocations(
    options: list[AgentResult], available_units: int, policy: PolicySpec
) -> list[tuple[str, list[PlanAllocation]]]:
    """Enumerate bounded single and hybrid allocations. Never exceeds available units."""
    candidates: list[tuple[str, list[PlanAllocation]]] = []

    # singles
    for option in options:
        units = min(available_units, int(option.expected_units_cleared))
        if units <= 0:
            continue
        candidates.append(("single", [_scale(option, units, policy)]))

    # hybrids over 2 and 3 strategies
    for size in (2, 3):
        if len(options) < size:
            continue
        for combo in itertools.combinations(options, size):
            for weights in _weights(size, policy.hybrid_weight_steps):
                allocations: list[PlanAllocation] = []
                remaining = available_units
                for option, weight in zip(combo, weights):
                    capacity = min(remaining, int(option.expected_units_cleared))
                    units = min(capacity, int(remaining * weight))
                    if units <= 0:
                        continue
                    allocations.append(_scale(option, units, policy))
                    remaining -= units
                if len(allocations) >= 2 and sum(a.units for a in allocations) <= available_units:
                    candidates.append(("hybrid", allocations))
    return candidates


def _plan_from_allocations(
    strategy: str, allocations: list[PlanAllocation], policy: PolicySpec
) -> RecoveryPlanDraft:
    total_units = sum(a.units for a in allocations)
    recovery = sum(a.expected_recovery for a in allocations)
    cost = sum(a.action_cost for a in allocations)
    net = sum(a.expected_net_recovery for a in allocations)
    confidence = (
        sum(a.confidence * a.units for a in allocations) / total_units if total_units else 0.0
    )
    # Cost basis of the allocated units is unknown here; the engine reports loss from the agents.
    return RecoveryPlanDraft(
        strategy="hybrid" if strategy == "hybrid" else "single",
        allocations=allocations,
        expected_recovery=round(recovery, 2),
        expected_loss=0.0,
        total_action_cost=round(cost, 2),
        expected_net_recovery=round(net, 2),
        confidence=round(confidence, 4),
    )


def select_plan(
    results: list[AgentResult],
    available_units: int,
    policy: PolicySpec | None = None,
) -> RecoveryPlanDraft:
    """Pick the best single strategy, unless a hybrid strictly beats it.

    Guarantees: no strategy allocates units another already allocated, no negative units,
    no allocation above the agent's own clearing capacity, and non-negative comparison.
    """
    p = policy or PolicySpec()
    feasible = [r for r in results if r.feasible and compute_net_recovery(r, p) > 0]
    if not feasible or available_units <= 0:
        return RecoveryPlanDraft(
            strategy="single",
            allocations=[],
            explanation=(
                "No acceptable recovery path exists for this stock: every strategy is either "
                "infeasible or produces a negative expected net recovery."
            ),
        )

    candidates = _candidate_allocations(feasible, available_units, p)
    if not candidates:
        return RecoveryPlanDraft(
            strategy="single",
            allocations=[],
            explanation="No strategy could be allocated without exceeding available stock.",
        )

    best_single_net = max(
        (sum(a.expected_net_recovery for a in allocs) for strategy, allocs in candidates if strategy == "single"),
        default=float("-inf"),
    )
    hybrids = [(s, a) for s, a in candidates if s == "hybrid"]
    best_hybrid = max(hybrids, key=lambda c: sum(x.expected_net_recovery for x in c[1]), default=None)

    if best_hybrid is not None:
        hybrid_net = sum(a.expected_net_recovery for a in best_hybrid[1])
        if best_single_net == float("-inf") or hybrid_net > best_single_net * (1 + p.hybrid_min_improvement):
            plan = _plan_from_allocations("hybrid", best_hybrid[1], p)
            plan.explanation = _explain(plan, available_units, best_single_net, best_hybrid=True)
            return plan

    best = max(
        (c for c in candidates if c[0] == "single"),
        key=lambda c: sum(a.expected_net_recovery for a in c[1]),
    )
    plan = _plan_from_allocations("single", best[1], p)
    plan.explanation = _explain(plan, available_units, best_single_net, best_hybrid=False)
    return plan


def _explain(plan: RecoveryPlanDraft, available_units: int, single_net: float, *, best_hybrid: bool) -> str:
    from app.agents import AGENT_LABELS

    parts = []
    if plan.strategy == "hybrid":
        split = ", ".join(f"{a.units} units → {AGENT_LABELS[a.agent]}" for a in plan.allocations)
        parts.append(
            f"Hybrid recovery on {available_units} units: {split}. Projected net recovery "
            f"{plan.expected_net_recovery:,.0f}, against {single_net:,.0f} for the best single "
            f"strategy — a {(plan.expected_net_recovery / single_net - 1):.1%} improvement."
        )
    else:
        winner = plan.allocations[0]
        parts.append(
            f"{AGENT_LABELS[winner.agent]} is selected for {winner.units} of {available_units} "
            f"units with an expected net recovery of {plan.expected_net_recovery:,.0f} "
            f"(gross {winner.expected_recovery:,.0f}, cost {winner.action_cost:,.0f})."
        )
    return " ".join(parts)


# --------------------------------------------------------------------------- context assembly


def _haversine(lat1, lon1, lat2, lon2) -> float:
    if None in (lat1, lon1, lat2, lon2):
        return 250.0
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _sale_points(db: Session, product_id: uuid.UUID, store_id: uuid.UUID, days: int = 200) -> list[SalePoint]:
    since = date.today() - timedelta(days=days)
    rows = db.scalars(
        select(Sale)
        .where(Sale.product_id == product_id, Sale.store_id == store_id, Sale.sold_on >= since)
        .order_by(Sale.sold_on)
    )
    return [
        SalePoint(sold_on=s.sold_on, quantity=s.quantity, unit_price=float(s.unit_price), is_promotion=s.is_promotion)
        for s in rows
    ]


def _product_spec(product: Product) -> ProductSpec:
    return ProductSpec(
        id=product.id,
        sku=product.sku,
        name=product.name,
        category=product.category.name,
        category_id=product.category_id,
        unit_cost=float(product.unit_cost),
        list_price=float(product.list_price),
        b2b_floor_pct=float(product.b2b_floor_pct),
        elasticity=float(product.category.elasticity),
        dimensions_cm=product.dimensions_cm,
    )


def _peer_stores(db: Session, product: Product, source_store_id: uuid.UUID, source_store: Store) -> list[StoreDemand]:
    rows = db.execute(
        select(Inventory, Store)
        .join(Store, Store.id == Inventory.store_id)
        .where(Inventory.product_id == product.id, Inventory.store_id != source_store_id)
    ).all()
    peers: list[StoreDemand] = []
    for inventory, store in rows:
        forecast = demand_forecast_service.forecast_for(db, product, store, inventory, persist=False)
        peers.append(
            StoreDemand(
                store=StoreSpec(
                    id=store.id,
                    code=store.code,
                    name=store.name,
                    city=store.city,
                    lat=float(store.lat) if store.lat is not None else None,
                    lon=float(store.lon) if store.lon is not None else None,
                ),
                quantity_on_hand=inventory.quantity,
                forecast_7d=forecast.forecast_7d,
                forecast_30d=forecast.forecast_30d,
                forecast_confidence=forecast.confidence,
                current_discount_pct=float(inventory.discount_pct),
                distance_km=round(
                    _haversine(
                        float(source_store.lat) if source_store.lat is not None else None,
                        float(source_store.lon) if source_store.lon is not None else None,
                        float(store.lat) if store.lat is not None else None,
                        float(store.lon) if store.lon is not None else None,
                    ),
                    2,
                ),
            )
        )
    return peers


def _co_purchase_rate(db: Session, store_id: uuid.UUID, product_id: uuid.UUID, other_id: uuid.UUID) -> float:
    """Share of days product B sold on which the anchor A also sold. A real same-basket proxy."""
    since = date.today() - timedelta(days=180)
    b_days = set(
        db.scalars(
            select(Sale.sold_on).where(
                Sale.product_id == product_id, Sale.store_id == store_id, Sale.sold_on >= since
            )
        )
    )
    if not b_days:
        return 0.0
    a_days = set(
        db.scalars(
            select(Sale.sold_on).where(
                Sale.product_id == other_id, Sale.store_id == store_id, Sale.sold_on >= since
            )
        )
    )
    return round(len(b_days & a_days) / len(b_days), 4)


def _bundle_candidates(db: Session, product: Product, store_id: uuid.UUID) -> list[BundleCandidate]:
    affinity_map: dict = product.category.co_purchase_affinity or {}
    candidates: list[BundleCandidate] = []
    rows = db.execute(
        select(Inventory, Product)
        .join(Product, Product.id == Inventory.product_id)
        .where(
            Inventory.store_id == store_id,
            Product.id != product.id,
            Product.is_active.is_(True),
            Inventory.quantity > 0,
        )
        .limit(40)
    ).all()
    for inventory, anchor in rows:
        affinity = float(affinity_map.get(anchor.category.name, 0.3))
        forecast_30d = demand_forecast_service.cached_forecast_30d(db, anchor.id, store_id)
        if forecast_30d < default_policy.min_anchor_demand * 0.5:
            continue
        candidates.append(
            BundleCandidate(
                product=_product_spec(anchor),
                store_id=store_id,
                quantity_on_hand=inventory.quantity,
                forecast_30d=forecast_30d,
                forecast_confidence=0.6,
                current_discount_pct=float(inventory.discount_pct),
                category_affinity=affinity,
                co_purchase_rate=_co_purchase_rate(db, store_id, product.id, anchor.id),
            )
        )
    candidates.sort(key=lambda c: (c.forecast_30d * c.category_affinity), reverse=True)
    return candidates[: default_policy.max_anchor_candidates * 2]


def _buyers(db: Session) -> list[BuyerSpec]:
    rows = db.scalars(select(B2BBuyer).where(B2BBuyer.is_active.is_(True)))
    return [
        BuyerSpec(
            id=b.id,
            business_name=b.business_name,
            required_categories=list(b.required_categories or []),
            location_city=b.location_city,
            lat=float(b.lat) if b.lat is not None else None,
            lon=float(b.lon) if b.lon is not None else None,
            required_quantity=b.required_quantity,
            maximum_budget=float(b.maximum_budget),
            preferred_unit_price=float(b.preferred_unit_price),
            reliability_score=float(b.reliability_score),
        )
        for b in rows
    ]


def build_context(
    db: Session,
    product: Product,
    store: Store,
    inventory: Inventory,
    *,
    policy: PolicySpec | None = None,
) -> RecoveryContext:
    p = policy or default_policy_spec()
    sales = _sale_points(db, product.id, store.id)
    forecast = demand_forecast_service.forecast_for(db, product, store, inventory, persist=True)
    metrics = dead_stock_service.compute_metrics(
        quantity=inventory.quantity,
        unit_cost=float(product.unit_cost),
        first_received_at=inventory.first_received_at,
        last_sold_at=inventory.last_sold_at,
        sales=sales,
        forecast_30d=forecast.forecast_30d,
        as_of=date.today(),
        policy=p,
    )
    previous = [
        float(pr.discount_pct)
        for pr in db.scalars(select(Promotion).where(Promotion.product_id == product.id))
    ]
    return RecoveryContext(
        product=_product_spec(product),
        store=StoreSpec(
            id=store.id,
            code=store.code,
            name=store.name,
            city=store.city,
            lat=float(store.lat) if store.lat is not None else None,
            lon=float(store.lon) if store.lon is not None else None,
        ),
        inventory={
            "quantity": inventory.quantity,
            "discount_pct": float(inventory.discount_pct),
            "first_received_at": inventory.first_received_at,
            "last_sold_at": inventory.last_sold_at,
            "location_code": inventory.location_code,
        },
        metrics=metrics,
        forecast=forecast,
        recent_sales=sales,
        previous_discounts=previous,
        peer_stores=_peer_stores(db, product, store.id, store),
        bundle_candidates=_bundle_candidates(db, product, store.id),
        b2b_buyers=_buyers(db),
        policy=p,
    )


def default_policy_spec() -> PolicySpec:
    """Project the settings object onto the agent-facing policy contract."""
    return PolicySpec(
        aging_days=default_policy.aging_days,
        no_sale_days=default_policy.no_sale_days,
        excess_stock_multiplier=default_policy.excess_stock_multiplier,
        min_margin_pct=default_policy.min_margin_pct,
        discount_candidates=list(default_policy.discount_candidates),
        transfer_base_handling=default_policy.transfer_base_handling,
        transfer_rate_per_km=default_policy.transfer_rate_per_km,
        transfer_max_units=default_policy.transfer_max_units,
        transfer_min_units=default_policy.transfer_min_units,
        transfer_avoided_markdown_pct=default_policy.transfer_avoided_markdown_pct,
        min_bundle_compatibility=default_policy.min_bundle_compatibility,
        min_anchor_demand=default_policy.min_anchor_demand,
        base_attach_rate=default_policy.base_attach_rate,
        reduced_price_factor=default_policy.reduced_price_factor,
        b2b_price_floor_pct=default_policy.b2b_price_floor_pct,
        b2b_target_price_factor=default_policy.b2b_target_price_factor,
        b2b_min_match_score=default_policy.b2b_min_match_score,
        max_anchor_candidates=default_policy.max_anchor_candidates,
        max_autonomous_discount=default_policy.max_autonomous_discount,
        hybrid_weight_steps=list(default_policy.hybrid_weight_steps),
        hybrid_min_improvement=default_policy.hybrid_min_improvement,
        min_plan_net_recovery_ratio=default_policy.min_plan_net_recovery_ratio,
        risk_penalty_weight=default_policy.risk_penalty_weight,
        friction_cost_ratio=dict(default_policy.friction_cost_ratio),
    )


# --------------------------------------------------------------------------- orchestration


def run_agents(ctx: RecoveryContext) -> list[AgentResult]:
    """Run all four agents. A single failing agent can never abort the analysis."""
    results: list[AgentResult] = []
    for agent_key, evaluate in AGENT_REGISTRY.items():
        try:
            results.append(evaluate(ctx))
        except Exception as exc:  # pragma: no cover - defensive isolation
            results.append(
                AgentResult.infeasible(
                    agent_key,  # type: ignore[arg-type]
                    f"Agent error ({type(exc).__name__}: {exc}). This strategy is unavailable; "
                    "others are unaffected.",
                )
            )
    return results


def analyze(db: Session, product_id: uuid.UUID, store_id: uuid.UUID, *, policy: PolicySpec | None = None):
    """Full analysis for one (product, store): context → agents → plan, persisted."""
    inventory = db.scalars(
        select(Inventory).where(Inventory.product_id == product_id, Inventory.store_id == store_id)
    ).first()
    if inventory is None:
        raise ValueError("No inventory row exists for that product and store.")
    product = db.get(Product, product_id)
    store = db.get(Store, store_id)
    if product is None or store is None:
        raise ValueError("Unknown product or store.")

    ctx = build_context(db, product, store, inventory, policy=policy)
    case = dead_stock_service.get_or_create_case(
        db, product=product, store=store, inventory=inventory, metrics=ctx.metrics, forecast_30d=ctx.forecast.forecast_30d
    )

    results = run_agents(ctx)
    for result in results:
        result.expected_net_recovery = compute_net_recovery(result, ctx.policy)
        _persist_agent_result(db, case.id, result)

    plan_draft = select_plan(results, ctx.available_units, ctx.policy)
    plan_draft.case_id = case.id

    from app.services import guardrail_service  # local import avoids a cycle

    plan_draft = guardrail_service.evaluate(plan_draft, ctx)

    plan = RecoveryPlan(
        case_id=case.id,
        strategy=plan_draft.strategy,
        allocations=[a.model_dump(mode="json") for a in plan_draft.allocations],
        expected_recovery=Decimal(str(plan_draft.expected_recovery)),
        expected_loss=Decimal(str(plan_draft.expected_loss)),
        total_action_cost=Decimal(str(plan_draft.total_action_cost)),
        expected_net_recovery=Decimal(str(plan_draft.expected_net_recovery)),
        confidence=Decimal(str(plan_draft.confidence)),
        guardrail_status=plan_draft.guardrail_status,
        guardrail_findings=[f.model_dump(mode="json") for f in plan_draft.guardrail_findings],
        explanation=plan_draft.explanation,
        status="planned" if plan_draft.guardrail_status != "blocked" else "blocked",
    )
    db.add(plan)
    case.status = "planned"
    db.flush()
    return case, ctx, results, plan, plan_draft


def _persist_agent_result(db: Session, case_id: uuid.UUID, result: AgentResult) -> None:
    existing = db.scalars(
        select(AgentResultRow).where(AgentResultRow.case_id == case_id, AgentResultRow.agent == result.agent)
    ).first()
    values = dict(
        feasible=result.feasible,
        reason_unavailable=result.reason_unavailable,
        expected_units_cleared=Decimal(str(result.expected_units_cleared)),
        expected_recovery=Decimal(str(result.expected_recovery)),
        expected_loss=Decimal(str(result.expected_loss)),
        action_cost=Decimal(str(result.action_cost)),
        expected_net_recovery=Decimal(str(result.expected_net_recovery)),
        confidence=Decimal(str(result.confidence)),
        reasons=list(result.reasons),
        payload=result.payload,
    )
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
    else:
        db.add(AgentResultRow(case_id=case_id, agent=result.agent, **values))
