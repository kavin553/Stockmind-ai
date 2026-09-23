"""StockMind AI — the FOUR specialized agents.

Exactly four AI agents exist in this product:

* ``discount``         — Discount Agent
* ``inter_store_swap`` — Inter-Store Swap Agent
* ``buy_a_get_b``      — Buy-A-Get-B Combo Agent
* ``b2b_bulk_buyer``   — B2B Bulk Buyer Agent

Everything else (dead-stock detection, forecasting, the recovery decision engine, guardrails,
execution, verification, audit) is a normal software service and is deliberately named as such.
"""
from app.agents import (
    b2b_bulk_buyer_agent,
    buy_a_get_b_agent,
    discount_agent,
    inter_store_swap_agent,
)

AGENT_REGISTRY = {
    "discount": discount_agent.evaluate,
    "inter_store_swap": inter_store_swap_agent.evaluate,
    "buy_a_get_b": buy_a_get_b_agent.evaluate,
    "b2b_bulk_buyer": b2b_bulk_buyer_agent.evaluate,
}

AGENT_LABELS = {
    "discount": "Discount Agent",
    "inter_store_swap": "Inter-Store Swap Agent",
    "buy_a_get_b": "Buy-A-Get-B Combo Agent",
    "b2b_bulk_buyer": "B2B Bulk Buyer Agent",
}

__all__ = [
    "discount_agent",
    "inter_store_swap_agent",
    "buy_a_get_b_agent",
    "b2b_bulk_buyer_agent",
    "AGENT_REGISTRY",
    "AGENT_LABELS",
]
