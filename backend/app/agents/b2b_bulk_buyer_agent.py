"""B2B BULK BUYER AGENT — place hard-to-clear inventory with a bulk buyer.

The buyer marketplace is a demo dataset, but the matching, price discovery and economics are
computed. Buyers are scored on category match, quantity fit, price compatibility, urgency,
proximity and reliability. The offer never goes below the configured cost floor.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from app.schemas.domain import AgentResult, BuyerSpec, RecoveryContext

AGENT = "b2b_bulk_buyer"

WEIGHTS = {
    "category_match": 0.30,
    "quantity_fit": 0.20,
    "price_compatibility": 0.15,
    "urgency": 0.15,
    "proximity": 0.10,
    "reliability": 0.10,
}


def haversine_km(lat1: float | None, lon1: float | None, lat2: float | None, lon2: float | None) -> float:
    if None in (lat1, lon1, lat2, lon2):
        return 250.0  # unknown geography → neutral-ish penalty, never zero
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def price_floor(ctx: RecoveryContext, buyer: BuyerSpec) -> float:
    return max(
        float(ctx.product.unit_cost) * float(ctx.product.b2b_floor_pct),
        float(ctx.product.unit_cost) * ctx.policy.b2b_price_floor_pct,
    )


def score_buyer(ctx: RecoveryContext, buyer: BuyerSpec, distance_km: float) -> dict:
    stock = float(ctx.inventory.quantity)
    category_match = 1.0 if ctx.product.category in buyer.required_categories else 0.0
    quantity_fit = min(stock, float(buyer.required_quantity)) / max(stock, float(buyer.required_quantity), 1.0)
    floor = price_floor(ctx, buyer)
    if buyer.preferred_unit_price <= 0:
        price_compatibility = 0.0
    else:
        price_compatibility = max(
            0.0,
            min(1.0, buyer.preferred_unit_price / max(floor, 1.0))
            - 0.5 * max(0.0, (floor - buyer.preferred_unit_price) / max(floor, 1.0)),
        )
    urgency = float(ctx.metrics.risk_score)
    proximity = max(0.0, 1.0 - distance_km / 1000.0)
    reliability = float(buyer.reliability_score)
    total = (
        WEIGHTS["category_match"] * category_match
        + WEIGHTS["quantity_fit"] * quantity_fit
        + WEIGHTS["price_compatibility"] * price_compatibility
        + WEIGHTS["urgency"] * urgency
        + WEIGHTS["proximity"] * proximity
        + WEIGHTS["reliability"] * reliability
    )
    return {
        "category_match": category_match,
        "quantity_fit": round(quantity_fit, 4),
        "price_compatibility": round(price_compatibility, 4),
        "urgency": round(urgency, 4),
        "proximity": round(proximity, 4),
        "reliability": round(reliability, 4),
        "distance_km": round(distance_km, 1),
        "match_score": round(total, 4),
        "price_floor": round(floor, 2),
    }


def evaluate(ctx: RecoveryContext) -> AgentResult:
    stock = float(ctx.inventory.quantity)
    if stock <= 0:
        return AgentResult.infeasible(AGENT, "No stock available for a bulk sale.")
    if not ctx.b2b_buyers:
        return AgentResult.infeasible(
            AGENT, "No B2B buyers are registered in the marketplace for this category."
        )

    cost = float(ctx.product.unit_cost)
    list_price = float(ctx.product.list_price)
    evaluated: list[dict] = []

    for buyer in ctx.b2b_buyers:
        distance = haversine_km(
            ctx.store.lat, ctx.store.lon, buyer.lat, buyer.lon
        )
        scored = score_buyer(ctx, buyer, distance)
        base = {
            "buyer_id": str(buyer.id),
            "buyer_name": buyer.business_name,
            "location": buyer.location_city,
            **scored,
        }
        if scored["category_match"] < 1.0:
            base.update({"eligible": False, "reason": "Buyer does not buy this category."})
            evaluated.append(base)
            continue

        floor = scored["price_floor"]
        if buyer.preferred_unit_price < floor:
            base.update(
                {
                    "eligible": False,
                    "reason": (
                        f"Buyer's preferred price {buyer.preferred_unit_price:,.0f} is below the "
                        f"cost floor {floor:,.0f}."
                    ),
                }
            )
            evaluated.append(base)
            continue

        ask = max(floor, min(buyer.preferred_unit_price, list_price * ctx.policy.b2b_target_price_factor))
        max_affordable = (float(buyer.maximum_budget) / ask) if ask > 0 else 0.0
        quantity = min(stock, max_affordable)
        # Honour the buyer's minimum lot; whole units only.
        quantity = float(int(quantity))
        if quantity < buyer.required_quantity:
            base.update(
                {
                    "eligible": False,
                    "reason": (
                        f"Only {quantity:.0f} units fit the buyer's budget, below their "
                        f"{buyer.required_quantity}-unit minimum lot."
                    ),
                }
            )
            evaluated.append(base)
            continue

        recovery = quantity * ask
        loss = quantity * cost - recovery
        base.update(
            {
                "eligible": scored["match_score"] >= ctx.policy.b2b_min_match_score,
                "offer_price": round(ask, 2),
                "quantity": quantity,
                "expected_recovery": round(recovery, 2),
                "expected_loss": round(loss, 2),
                "budget_utilisation": round(recovery / max(1.0, float(buyer.maximum_budget)), 4),
                "reason": (
                    "" if scored["match_score"] >= ctx.policy.b2b_min_match_score
                    else f"Match score {scored['match_score']:.2f} below threshold."
                ),
            }
        )
        evaluated.append(base)

    eligible = [e for e in evaluated if e.get("eligible")]
    if not eligible:
        return AgentResult(
            agent=AGENT,
            feasible=False,
            reason_unavailable=(
                f"No B2B buyer can absorb this stock at or above the cost floor "
                f"(evaluated {len(ctx.b2b_buyers)} buyers)."
            ),
            payload={"buyers": evaluated},
        )

    best = max(eligible, key=lambda e: e["expected_recovery"])
    confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.55 * best["match_score"]
                + 0.25 * best["reliability"]
                + 0.20 * min(1.0, best["quantity"] / max(1.0, stock)),
            ),
        ),
        4,
    )

    above_cost = best["offer_price"] - cost
    reasons = [
        f"{best['buyer_name']} ({best['location']}) requires "
        f"{best['quantity']:.0f} units in {ctx.product.category} and is "
        f"{best['distance_km']:.0f} km away (match score {best['match_score']:.2f}).",
        f"Offer lands at {best['offer_price']:,.2f}/unit — {above_cost:,.2f} above unit cost and "
        f"above the {best['price_floor']:,.2f} floor — recovering "
        f"{best['expected_recovery']:,.0f} in one transaction.",
        f"Buyer reliability is {best['reliability']:.2f}; the deal uses "
        f"{best['budget_utilisation']:.0%} of their stated budget.",
    ]
    for e in evaluated:
        if not e.get("eligible"):
            reasons.append(f"{e['buyer_name']} rejected: {e.get('reason', 'not eligible')}")

    return AgentResult(
        agent=AGENT,
        feasible=True,
        expected_units_cleared=round(best["quantity"], 2),
        expected_recovery=round(best["expected_recovery"], 2),
        expected_loss=round(best["expected_loss"], 2),
        action_cost=0.0,
        confidence=confidence,
        reasons=reasons,
        payload={"best_buyer": best, "buyers": evaluated},
    )


run = evaluate
