"""Direct agent invocation endpoints.

Useful for tests, for the Recovery Studio's per-agent re-evaluation, and for demonstrating
that each agent works on structured input independently.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AGENT_REGISTRY, AGENT_LABELS
from app.api.deps import current_user, db_session, parse_uuid
from app.models import Inventory, Product, Store, User
from app.schemas.domain import RecoveryContext
from app.services import recovery_engine

router = APIRouter(prefix="/agents", tags=["agents"])

AGENT_KEYS = {
    "discount": "discount",
    "inter-store-swap": "inter_store_swap",
    "inter_store_swap": "inter_store_swap",
    "buy-a-get-b": "buy_a_get_b",
    "buy_a_get_b": "buy_a_get_b",
    "b2b": "b2b_bulk_buyer",
    "b2b_bulk_buyer": "b2b_bulk_buyer",
}


class AgentRequest(BaseModel):
    product_id: str | None = None
    store_code: str | None = None
    store_id: str | None = None
    context: RecoveryContext | None = None


@router.post("/discount")
def discount(payload: AgentRequest, db: Session = Depends(db_session), user: User = Depends(current_user)) -> dict:
    return _run("discount", payload, db)


@router.post("/inter-store-swap")
def inter_store_swap(payload: AgentRequest, db: Session = Depends(db_session), user: User = Depends(current_user)) -> dict:
    return _run("inter_store_swap", payload, db)


@router.post("/buy-a-get-b")
def buy_a_get_b(payload: AgentRequest, db: Session = Depends(db_session), user: User = Depends(current_user)) -> dict:
    return _run("buy_a_get_b", payload, db)


@router.post("/b2b")
def b2b(payload: AgentRequest, db: Session = Depends(db_session), user: User = Depends(current_user)) -> dict:
    return _run("b2b_bulk_buyer", payload, db)


def _run(agent: str, payload: AgentRequest, db: Session) -> dict:
    ctx = payload.context or _context(db, payload)
    try:
        result = AGENT_REGISTRY[agent](ctx)
    except Exception as exc:  # defensive: an agent must never take the API down
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"{AGENT_LABELS[agent]} failed to evaluate: {type(exc).__name__}: {exc}",
        ) from None
    result.expected_net_recovery = recovery_engine.compute_net_recovery(result, ctx.policy)
    return {
        "label": AGENT_LABELS[agent],
        "result": result.model_dump(mode="json"),
        "available_units": ctx.available_units,
    }


def _context(db: Session, payload: AgentRequest) -> RecoveryContext:
    if not payload.product_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide product_id or a full context.")
    product = db.get(Product, parse_uuid(payload.product_id, "product id"))
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
    store = _store(db, payload)
    inventory = db.scalars(
        select(Inventory).where(Inventory.product_id == product.id, Inventory.store_id == store.id)
    ).first()
    if inventory is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No inventory for that product at that store.")
    return recovery_engine.build_context(db, product, store, inventory)


def _store(db: Session, payload: AgentRequest) -> Store:
    stmt = select(Store)
    if payload.store_id:
        stmt = stmt.where(Store.id == parse_uuid(payload.store_id, "store id"))
    elif payload.store_code:
        stmt = stmt.where(Store.code == payload.store_code)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide store_id or store_code.")
    store = db.scalars(stmt).first()
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")
    return store
