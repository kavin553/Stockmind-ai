"""GUARDRAIL SERVICE (deterministic policy layer — not an AI agent).

Runs **after** the agents and **before** execution. Findings are additive:

* ``info``  — recorded, does not block.
* ``flag``  — allowed but requires manual review before/after execution.
* ``block`` — the plan may not be executed.

The service is pure: it takes a plan draft plus the context and returns an annotated draft.
"""
from __future__ import annotations

from app.schemas.domain import GuardrailFinding, RecoveryContext, RecoveryPlanDraft


def evaluate(plan: RecoveryPlanDraft, ctx: RecoveryContext) -> RecoveryPlanDraft:
    findings: list[GuardrailFinding] = []
    p = ctx.policy
    available = float(ctx.available_units)
    unit_cost = float(ctx.product.unit_cost)
    capital_locked = max(0.0, ctx.metrics.capital_locked)

    def add(code: str, severity: str, message: str, agent: str | None = None) -> None:
        findings.append(GuardrailFinding(code=code, severity=severity, message=message, agent=agent))

    if not plan.allocations:
        add("no_feasible_plan", "block", "No feasible recovery strategy was produced for this stock.")
    else:
        total_units = sum(a.units for a in plan.allocations)
        if total_units > available:
            add(
                "quantity_limit",
                "block",
                f"Plan allocates {total_units} units but only {available:.0f} are on hand.",
            )
        if any(a.units <= 0 for a in plan.allocations):
            add("non_positive_quantity", "block", "A strategy allocated zero or negative units.")
        if total_units < 1:
            add("zero_allocation", "block", "The plan clears no units at all.")

        for allocation in plan.allocations:
            agent = allocation.agent
            detail = allocation.detail or {}

            if agent == "discount":
                discount = detail.get("recommended_discount")
                if discount is not None and float(discount) > p.max_autonomous_discount:
                    add(
                        "max_autonomous_discount",
                        "flag",
                        f"Discount of {float(discount):.0%} exceeds the "
                        f"{p.max_autonomous_discount:.0%} autonomous ceiling — manual review required.",
                        agent=agent,
                    )
                elif discount is not None:
                    add(
                        "discount_within_policy",
                        "info",
                        f"Discount of {float(discount):.0%} is within the autonomous ceiling.",
                        agent=agent,
                    )

            if agent == "inter_store_swap":
                if allocation.units > p.transfer_max_units:
                    add(
                        "transfer_limit",
                        "block",
                        f"Transfer of {allocation.units} units exceeds the per-move limit of "
                        f"{p.transfer_max_units}.",
                        agent=agent,
                    )
                if allocation.units < p.transfer_min_units:
                    add(
                        "transfer_minimum",
                        "flag",
                        f"Transfer of {allocation.units} units is below the {p.transfer_min_units}-unit "
                        "minimum and may not be worth executing.",
                        agent=agent,
                    )
                if not detail.get("destination_store_id"):
                    add("transfer_destination_missing", "block", "Transfer has no destination store.", agent=agent)

            if agent == "b2b_bulk_buyer":
                offer = detail.get("offer_price")
                floor = unit_cost * p.b2b_price_floor_pct
                if offer is None:
                    add("b2b_price_missing", "block", "B2B offer has no price.", agent=agent)
                elif float(offer) < floor:
                    add(
                        "b2b_price_floor",
                        "block",
                        f"B2B offer of {float(offer):,.2f}/unit is below the "
                        f"{floor:,.2f}/unit cost floor.",
                        agent=agent,
                    )

            if agent == "buy_a_get_b":
                anchor = detail.get("product_a_sku")
                if not anchor or anchor == ctx.product.sku:
                    add(
                        "invalid_product_combination",
                        "block",
                        "Bundle pairs the dead-stock product with itself or has no anchor.",
                        agent=agent,
                    )

            if allocation.expected_net_recovery < 0:
                add(
                    "negative_net_recovery",
                    "block",
                    f"{agent} produces a negative expected net recovery "
                    f"({allocation.expected_net_recovery:,.2f}).",
                    agent=agent,
                )

        if plan.expected_net_recovery < 0:
            add(
                "negative_expected_recovery",
                "block",
                "The plan's total expected net recovery is negative.",
            )
        elif capital_locked > 0:
            ratio = plan.expected_net_recovery / capital_locked
            if ratio < p.min_plan_net_recovery_ratio:
                add(
                    "min_recovery_ratio",
                    "flag",
                    f"Expected net recovery is {ratio:.1%} of locked capital, below the "
                    f"{p.min_plan_net_recovery_ratio:.0%} policy floor — manual review recommended.",
                )
            else:
                add(
                    "min_recovery_ratio",
                    "info",
                    f"Expected net recovery is {ratio:.1%} of locked capital.",
                )

    if any(f.severity == "block" for f in findings):
        plan.guardrail_status = "blocked"
    elif any(f.severity == "flag" for f in findings):
        plan.guardrail_status = "flagged"
    else:
        plan.guardrail_status = "passed"
    plan.guardrail_findings = findings
    return plan


def is_executable(plan: RecoveryPlanDraft) -> bool:
    return plan.guardrail_status != "blocked" and len(plan.allocations) > 0
