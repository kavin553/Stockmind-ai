"""INTER-STORE SWAP AGENT — should this stock move to a store with stronger demand?

A transfer is only proposed when the destination's forecast genuinely exceeds what it
already holds, the moved quantity is worthwhile, and the freight is smaller than the
markdown the source would otherwise have to take.
"""
from __future__ import annotations

from app.schemas.domain import AgentResult, RecoveryContext

AGENT = "inter_store_swap"


def _distance_penalty_confidence(distance_km: float) -> float:
    """Close destinations keep more of the modelled value; 0 km → 1.0, 500 km → ~0.55."""
    return max(0.35, 1.0 / (1.0 + distance_km / 400.0))


def transfer_cost(ctx: RecoveryContext, quantity: float, distance_km: float) -> float:
    p = ctx.policy
    return quantity * (p.transfer_base_handling + p.transfer_rate_per_km * distance_km)


def evaluate(ctx: RecoveryContext) -> AgentResult:
    stock = ctx.inventory.quantity
    if stock <= 0:
        return AgentResult.infeasible(AGENT, "No stock available to transfer.")
    if not ctx.peer_stores:
        return AgentResult.infeasible(
            AGENT, "No peer stores are configured, so no destination demand can be assessed."
        )

    list_price = float(ctx.product.list_price)
    unit_cost = float(ctx.product.unit_cost)
    markdown_price = list_price * (1.0 - ctx.policy.transfer_avoided_markdown_pct)
    evaluated: list[dict] = []

    for peer in ctx.peer_stores:
        if peer.quantity_on_hand <= 0 and peer.forecast_30d <= 0:
            evaluated.append(
                {
                    "destination_store": peer.store.code,
                    "transfer_quantity": 0,
                    "eligible": False,
                    "reason": "No demand or stock signal at destination.",
                }
            )
            continue

        headroom = max(0.0, peer.forecast_30d - peer.quantity_on_hand)
        # Destination discounts reduce the realised price there.
        destination_price = list_price * (1.0 - peer.current_discount_pct)
        source_price = markdown_price
        if destination_price <= source_price:
            evaluated.append(
                {
                    "destination_store": peer.store.code,
                    "transfer_quantity": 0,
                    "eligible": False,
                    "reason": (
                        "Destination already discounts at or below the source's expected "
                        "markdown price."
                    ),
                }
            )
            continue

        qty = min(float(stock), headroom, float(ctx.policy.transfer_max_units))
        cost = transfer_cost(ctx, qty, peer.distance_km)
        recovery = qty * destination_price
        net = recovery - cost
        eligible = qty >= ctx.policy.transfer_min_units and net > 0
        evaluated.append(
            {
                "destination_store": peer.store.code,
                "destination_store_id": str(peer.store.id),
                "destination_city": peer.store.city,
                "distance_km": round(peer.distance_km, 1),
                "forecast_30d": peer.forecast_30d,
                "quantity_on_hand": peer.quantity_on_hand,
                "headroom": round(headroom, 2),
                "transfer_quantity": round(qty, 2),
                "transfer_cost": round(cost, 2),
                "expected_recovery": round(recovery, 2),
                "avoided_markdown": round(qty * (list_price - source_price), 2),
                "expected_loss": round(qty * unit_cost - recovery, 2),
                "net_before_risk": round(net, 2),
                "eligible": eligible,
                "reason": (
                    "" if eligible else
                    f"Below the {ctx.policy.transfer_min_units}-unit minimum move."
                    if qty < ctx.policy.transfer_min_units
                    else "Freight exceeds the value recovered."
                ),
            }
        )

    eligible = [e for e in evaluated if e["eligible"]]
    if not eligible:
        return AgentResult(
            agent=AGENT,
            feasible=False,
            reason_unavailable=(
                "No destination store shows enough uncovered demand to justify a transfer "
                f"(evaluated {len(ctx.peer_stores)} stores)."
            ),
            payload={"destinations": evaluated},
        )

    best = max(eligible, key=lambda e: e["net_before_risk"])
    demand_confidence = min(1.0, best["forecast_30d"] / max(1.0, best["quantity_on_hand"] + best["transfer_quantity"]))
    confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.45 * float(best["forecast_30d"] > 0)
                + 0.25 * _distance_penalty_confidence(best["distance_km"])
                + 0.20 * demand_confidence
                + 0.10 * float(ctx.forecast.confidence),
            ),
        ),
        4,
    )

    reasons = [
        f"Moving {best['transfer_quantity']:.0f} units from {ctx.store.code} to "
        f"{best['destination_store']} ({best['destination_city']}) costs "
        f"{best['transfer_cost']:,.0f} in freight.",
        f"{best['destination_store']} forecasts {best['forecast_30d']:.0f} units of 30-day "
        f"demand against {best['quantity_on_hand']} on hand, leaving "
        f"{best['headroom']:.0f} units of uncovered demand.",
        f"The transfer recovers {best['expected_recovery']:,.0f} at full destination price, "
        f"avoiding a {ctx.policy.transfer_avoided_markdown_pct:.0%} markdown worth "
        f"{best['avoided_markdown']:,.0f}.",
    ]
    for e in evaluated:
        if not e["eligible"] and e["destination_store"] != best["destination_store"]:
            reasons.append(f"{e['destination_store']} rejected: {e['reason']}")

    return AgentResult(
        agent=AGENT,
        feasible=True,
        expected_units_cleared=round(best["transfer_quantity"], 2),
        expected_recovery=round(best["expected_recovery"], 2),
        expected_loss=round(best["expected_loss"], 2),
        action_cost=round(best["transfer_cost"], 2),
        confidence=confidence,
        reasons=reasons,
        payload={"best_destination": best, "destinations": evaluated},
    )


run = evaluate
