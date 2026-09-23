"""BUY-A-GET-B COMBO AGENT — use a high-demand product A to clear dead-stock product B.

Pairing is computed, never random. Compatibility blends category affinity (seed data),
observed co-purchase, price-band similarity and the anchor's margin room. Only anchors with
genuine demand and adequate compatibility are considered.
"""
from __future__ import annotations

from app.schemas.domain import AgentResult, BundleCandidate, RecoveryContext

AGENT = "buy_a_get_b"

# offer type -> (attach multiplier, share of B's list price actually collected, A units per B)
OFFER_TYPES: dict[str, tuple[float, float, float]] = {
    "buy_a_get_b_free": (1.00, 0.0, 1.0),
    "buy_a_get_b_reduced": (0.75, 0.60, 1.0),
    "buy_2a_get_b": (0.55, 0.0, 2.0),
    "bundle_ab": (0.85, 0.50, 1.0),
}

INCREMENTAL_ANCHOR_SHARE = 0.25  # share of anchor-driven sales that would not have happened anyway


def price_band_similarity(price_a: float, price_b: float) -> float:
    hi = max(price_a, price_b, 1.0)
    return max(0.0, 1.0 - abs(price_a - price_b) / hi)


def margin_room(price: float, cost: float) -> float:
    """Gross-margin ratio normalised to a 50% ceiling — how much of a giveaway A can absorb."""
    if price <= 0:
        return 0.0
    return max(0.0, min(1.0, ((price - cost) / price) / 0.5))


def compatibility(ctx: RecoveryContext, candidate: BundleCandidate) -> float:
    return round(
        max(
            0.0,
            min(
                1.0,
                0.40 * candidate.category_affinity
                + 0.25 * candidate.co_purchase_rate
                + 0.20 * price_band_similarity(
                    float(candidate.product.list_price), float(ctx.product.list_price)
                )
                + 0.15 * margin_room(
                    float(candidate.product.list_price), float(candidate.product.unit_cost)
                ),
            ),
        ),
        4,
    )


def _best_offer(ctx: RecoveryContext, candidate: BundleCandidate, compat: float) -> dict:
    stock_b = float(ctx.inventory.quantity)
    price_b = float(ctx.product.list_price)
    cost_b = float(ctx.product.unit_cost)
    price_a = float(candidate.product.list_price)
    cost_a = float(candidate.product.unit_cost)

    demand_factor = max(0.0, min(1.5, candidate.forecast_30d / max(1.0, ctx.policy.min_anchor_demand)))
    offers = []
    for offer_type, (attach_mult, collected_share, a_per_b) in OFFER_TYPES.items():
        attach = ctx.policy.base_attach_rate * compat * demand_factor * attach_mult
        attach = max(0.0, min(0.75, attach))
        predicted_b = min(stock_b, candidate.forecast_30d) * attach
        realised_b = predicted_b * price_b * collected_share
        # Only a conservative share of anchor sales is treated as truly incremental.
        incremental_a = predicted_b * a_per_b * (price_a - cost_a) * INCREMENTAL_ANCHOR_SHARE
        recovery = realised_b + incremental_a
        loss = predicted_b * cost_b - incremental_a
        giveaway = predicted_b * price_b * (1.0 - collected_share)
        offers.append(
            {
                "bundle_type": offer_type,
                "attach_rate": round(attach, 4),
                "predicted_units_cleared": round(predicted_b, 2),
                "realised_revenue_b": round(realised_b, 2),
                "incremental_anchor_margin": round(incremental_a, 2),
                "giveaway_value": round(giveaway, 2),
                "expected_recovery": round(recovery, 2),
                "expected_loss": round(loss, 2),
            }
        )
    return max(offers, key=lambda o: o["expected_recovery"])


def evaluate(ctx: RecoveryContext) -> AgentResult:
    if ctx.inventory.quantity <= 0:
        return AgentResult.infeasible(AGENT, "No product B stock on hand to bundle.")
    if not ctx.bundle_candidates:
        return AgentResult.infeasible(
            AGENT, "No high-demand anchor products are available in compatible categories."
        )

    evaluated: list[dict] = []
    for candidate in ctx.bundle_candidates[: ctx.policy.max_anchor_candidates]:
        if candidate.product.id == ctx.product.id:
            continue  # never pair B with itself
        compat = compatibility(ctx, candidate)
        eligible = (
            compat >= ctx.policy.min_bundle_compatibility
            and candidate.forecast_30d >= ctx.policy.min_anchor_demand
        )
        entry: dict = {
            "product_a_sku": candidate.product.sku,
            "product_a_name": candidate.product.name,
            "product_a_id": str(candidate.product.id),
            "category_affinity": candidate.category_affinity,
            "co_purchase_rate": candidate.co_purchase_rate,
            "anchor_forecast_30d": candidate.forecast_30d,
            "compatibility": compat,
            "eligible": eligible,
        }
        if eligible:
            entry.update(_best_offer(ctx, candidate, compat))
        else:
            entry["reason"] = (
                "Compatibility below the pairing threshold."
                if compat < ctx.policy.min_bundle_compatibility
                else f"Anchor demand {candidate.forecast_30d:.0f} below the "
                f"{ctx.policy.min_anchor_demand:.0f}-unit minimum."
            )
        evaluated.append(entry)

    eligible = [e for e in evaluated if e["eligible"]]
    if not eligible:
        return AgentResult(
            agent=AGENT,
            feasible=False,
            reason_unavailable=(
                "No compatible high-demand anchor product exists to carry this dead stock."
            ),
            payload={"candidates": evaluated},
        )

    best = max(eligible, key=lambda e: e["expected_recovery"])
    confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.45 * best["compatibility"]
                + 0.30 * float(best["anchor_forecast_30d"] > 0) * min(1.0, best["anchor_forecast_30d"] / 100.0)
                + 0.15 * ctx.forecast.confidence
                + 0.10 * float(best["co_purchase_rate"] > 0),
            ),
        ),
        4,
    )

    reasons = [
        f"Paired with {best['product_a_sku']} ({best['product_a_name']}): 30-day anchor demand "
        f"{best['anchor_forecast_30d']:.0f} units, category affinity "
        f"{best['category_affinity']:.2f}, compatibility score {best['compatibility']:.2f}.",
        f"Offer '{best['bundle_type']}' with an estimated attach rate of "
        f"{best['attach_rate']:.1%} clears {best['predicted_units_cleared']:.0f} dead-stock units, "
        f"recovering {best['expected_recovery']:,.0f}.",
        f"The anchor contributes {best['incremental_anchor_margin']:,.0f} of margin; the "
        f"giveaway is valued at {best['giveaway_value']:,.0f}.",
    ]
    for e in evaluated:
        if not e["eligible"]:
            reasons.append(f"{e['product_a_sku']} rejected: {e.get('reason', 'not eligible')}")

    return AgentResult(
        agent=AGENT,
        feasible=True,
        expected_units_cleared=round(best["predicted_units_cleared"], 2),
        expected_recovery=round(best["expected_recovery"], 2),
        expected_loss=round(best["expected_loss"], 2),
        action_cost=0.0,
        confidence=confidence,
        reasons=reasons,
        payload={"best_offer": best, "candidates": evaluated},
    )


run = evaluate
