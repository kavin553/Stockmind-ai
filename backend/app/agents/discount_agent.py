"""DISCOUNT AGENT — can controlled discounting clear the dead stock acceptably?

Pure function over a :class:`RecoveryContext`. No ORM access, no exceptions on bad input —
insufficient data yields ``feasible=False`` with an explanation.

Definition of the reported economics (identical across all four agents):

* ``expected_recovery`` — cash/value actually recovered by the action.
* ``expected_loss`` — cost basis of the cleared units minus the recovery. A negative value
  means the action clears above cost (a gain). Action costs are tracked separately in
  ``action_cost`` and again in the engine's net calculation.
"""
from __future__ import annotations

import statistics

from app.schemas.domain import AgentResult, DiscountScenario, RecoveryContext, SalePoint

AGENT = "discount"


def _history_days(sales: list[SalePoint]) -> int:
    if not sales:
        return 0
    days = sorted(s.sold_on for s in sales)
    return max(0, (days[-1] - days[0]).days)


def _sales_regularity(sales: list[SalePoint]) -> float:
    """1.0 for a perfectly steady seller, → 0 for erratic/intermittent sales."""
    if len(sales) < 3:
        return 0.0
    quantities = [s.quantity for s in sales]
    mean = statistics.fmean(quantities)
    if mean <= 0:
        return 0.0
    cv = statistics.pstdev(quantities) / mean
    return max(0.0, min(1.0, 1.0 - cv))


def _observed_response(sales: list[SalePoint]) -> float | None:
    """Observed promo lift (promo avg units / non-promo avg units), or None if unknown."""
    promo = [s.quantity for s in sales if s.is_promotion]
    regular = [s.quantity for s in sales if not s.is_promotion]
    if len(promo) < 3 or len(regular) < 3:
        return None
    base = statistics.fmean(regular)
    if base <= 0:
        return None
    return max(0.0, statistics.fmean(promo) / base - 1.0)


def _lift(discount: float, elasticity: float, observed: float | None, age_days: int) -> float:
    """Multiplicative unit lift for a discount level.

    Uses an arc-elasticity curve ``1 + e * d/(1-d)``. Where the SKU has measurable promo
    history, the observed response is blended in (weighted by how much history exists).
    A freshness damping factor reflects that dead stock converts discounts less efficiently
    than fresh stock.
    """
    d = min(max(discount, 0.0), 0.90)
    theoretical = elasticity * (d / (1.0 - d))
    if observed is not None:
        # Bridge from the observed response at the average historical discount, capped.
        theoretical = 0.5 * theoretical + 0.5 * min(observed * (d / 0.15), 4.0)
    freshness = 1.0 - 0.30 * min(1.0, age_days / 365.0)
    return max(1.0, 1.0 + theoretical * freshness)


def _scenario(ctx: RecoveryContext, discount: float, observed: float | None) -> DiscountScenario:
    stock = float(ctx.inventory.quantity)
    list_price = float(ctx.product.list_price)
    unit_cost = float(ctx.product.unit_cost)
    elasticity = float(ctx.product.elasticity)
    baseline_30d = float(ctx.forecast.forecast_30d)

    lift = _lift(discount, elasticity, observed, ctx.metrics.age_days)
    predicted = min(stock, max(0.0, baseline_30d * lift))
    effective_price = list_price * (1.0 - discount)
    revenue = predicted * effective_price
    margin = predicted * (effective_price - unit_cost)
    remaining = stock - predicted
    # Units left behind keep their cost basis locked; only the cleared units are valued here.
    recovery = revenue
    loss = predicted * unit_cost - recovery
    floor_price = unit_cost * (1.0 + ctx.policy.min_margin_pct)
    return DiscountScenario(
        discount_pct=round(discount, 4),
        predicted_units_cleared=round(predicted, 2),
        expected_revenue=round(revenue, 2),
        gross_margin=round(margin, 2),
        remaining_stock=round(remaining, 2),
        expected_recovery=round(recovery, 2),
        expected_loss=round(loss, 2),
        below_margin_floor=effective_price < floor_price,
    )


def _confidence(ctx: RecoveryContext, observed: float | None) -> float:
    history = _history_days(ctx.recent_sales)
    adequacy = min(1.0, history / 180.0)
    regularity = _sales_regularity(ctx.recent_sales)
    response_bonus = 0.1 if observed is not None else 0.0
    score = 0.4 * adequacy + 0.3 * float(ctx.forecast.confidence) + 0.3 * regularity + response_bonus
    return round(max(0.0, min(1.0, score)), 4)


def evaluate(ctx: RecoveryContext) -> AgentResult:
    stock = ctx.inventory.quantity
    if stock <= 0:
        return AgentResult.infeasible(AGENT, "No inventory on hand — nothing to discount.")
    if ctx.product.list_price <= 0:
        return AgentResult.infeasible(AGENT, "Product has no valid selling price.")
    if ctx.product.unit_cost <= 0:
        return AgentResult.infeasible(AGENT, "Product has no valid cost, so margin cannot be policed.")

    observed = _observed_response(ctx.recent_sales)
    scenarios = [_scenario(ctx, d, observed) for d in ctx.policy.discount_candidates]
    eligible = [s for s in scenarios if not s.below_margin_floor]

    if not eligible:
        cheapest = max(ctx.policy.discount_candidates)
        return AgentResult(
            agent=AGENT,
            feasible=False,
            reason_unavailable=(
                "Every discount scenario breaches the minimum margin floor "
                f"({ctx.policy.min_margin_pct:.0%} over unit cost); cheapest attempt was "
                f"{cheapest:.0%} off list."
            ),
            confidence=_confidence(ctx, observed),
            payload={"scenarios": [s.model_dump() for s in scenarios]},
        )

    # Rank by net contribution: recovery minus the promotional give-away on cleared units.
    def net(s: DiscountScenario) -> float:
        give_away = s.predicted_units_cleared * float(ctx.product.list_price) * s.discount_pct
        return s.expected_recovery - give_away

    best = max(eligible, key=net)
    confidence = _confidence(ctx, observed)

    covered = (best.expected_recovery / (stock * float(ctx.product.unit_cost))) if stock else 0.0
    reasons = [
        f"A {best.discount_pct:.0%} discount is estimated to clear "
        f"{best.predicted_units_cleared:.0f} of {stock} units within 30 days, "
        f"recovering {best.expected_recovery:,.0f} ({covered:.1%} of the "
        f"{stock * float(ctx.product.unit_cost):,.0f} locked in this SKU).",
        f"Estimated gross margin at that discount is {best.gross_margin:,.0f} "
        f"(unit price {float(ctx.product.list_price) * (1 - best.discount_pct):,.2f} vs cost "
        f"{float(ctx.product.unit_cost):,.2f}).",
    ]
    if best.remaining_stock > 0:
        reasons.append(
            f"{best.remaining_stock:.0f} units would still remain, so discounting alone is "
            "a partial recovery."
        )
    blockers = [s for s in scenarios if s.below_margin_floor]
    if blockers:
        lowest_blocked = min(blockers, key=lambda s: s.discount_pct)
        reasons.append(
            f"Scenarios from {lowest_blocked.discount_pct:.0%} upward are rejected: the price "
            f"falls below the cost-plus-margin floor."
        )
    if observed is not None:
        reasons.append(
            f"Past promotions on this SKU showed a {observed:.0%} unit response, which is "
            "blended into the lift estimate."
        )

    return AgentResult(
        agent=AGENT,
        feasible=True,
        expected_units_cleared=round(best.predicted_units_cleared, 2),
        expected_recovery=round(best.expected_recovery, 2),
        expected_loss=round(best.expected_loss, 2),
        action_cost=0.0,
        confidence=confidence,
        reasons=reasons,
        payload={
            "recommended_discount": best.discount_pct,
            "predicted_units_cleared": best.predicted_units_cleared,
            "expected_recovery": best.expected_recovery,
            "expected_loss": best.expected_loss,
            "remaining_stock": best.remaining_stock,
            "scenarios": [s.model_dump() for s in scenarios],
            "observed_response": observed,
        },
    )


run = evaluate
