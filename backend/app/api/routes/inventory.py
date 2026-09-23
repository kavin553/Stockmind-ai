from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, parse_uuid
from app.models import Category, Inventory, Product, Sale, Store, User
from app.services import dead_stock_service, demand_forecast_service, recovery_engine

router = APIRouter(tags=["inventory"])


@router.get("/inventory")
def list_inventory(
    store: str | None = None,
    category: str | None = None,
    q: str | None = None,
    sort: str = Query("value", pattern="^(value|quantity|age|sku)$"),
    direction: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(db_session),
    _: User = Depends(current_user),
) -> dict:
    stmt = select(Inventory).join(Product, Product.id == Inventory.product_id).join(Store, Store.id == Inventory.store_id)
    if store:
        stmt = stmt.where(Store.code == store)
    if category:
        stmt = stmt.join(Category, Category.id == Product.category_id).where(Category.name == category)
    if q:
        like = f"%{q.upper()}%"
        from sqlalchemy import or_

        stmt = stmt.where(or_(Product.sku.ilike(like), Product.name.ilike(f"%{q}%")))

    rows = list(db.scalars(stmt))
    items = []
    for inv in rows:
        product = inv.product
        value = inv.quantity * float(product.unit_cost)
        age = (date.today() - inv.first_received_at).days
        items.append(
            {
                "product_id": str(product.id),
                "store_id": str(inv.store_id),
                "sku": product.sku,
                "name": product.name,
                "category": product.category.name,
                "store": inv.store.code,
                "quantity": inv.quantity,
                "unit_cost": float(product.unit_cost),
                "list_price": float(product.list_price),
                "discount_pct": float(inv.discount_pct),
                "age_days": age,
                "last_sold_at": inv.last_sold_at.isoformat() if inv.last_sold_at else None,
                "location_code": inv.location_code,
                "inventory_value": round(value, 2),
            }
        )
    keys = {
        "value": lambda r: r["inventory_value"],
        "quantity": lambda r: r["quantity"],
        "age": lambda r: r["age_days"],
        "sku": lambda r: r["sku"],
    }
    items.sort(key=keys[sort], reverse=(direction == "desc"))
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start : start + page_size], "total": total, "page": page, "page_size": page_size}


@router.get("/dead-stock")
def list_dead_stock(
    store: str | None = None,
    category: str | None = None,
    risk: str | None = None,
    min_age: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(db_session),
    _: User = Depends(current_user),
) -> dict:
    store_id = None
    if store:
        store_row = db.scalars(select(Store).where(Store.code == store)).first()
        if store_row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown store '{store}'.")
        store_id = store_row.id
    category_id = None
    if category:
        category_row = db.scalars(select(Category).where(Category.name == category)).first()
        if category_row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown category '{category}'.")
        category_id = category_row.id

    rows = dead_stock_service.dead_stock_rows(
        db, store_id=store_id, category_id=category_id, risk_band=risk, limit=1000
    )
    if min_age is not None:
        rows = [r for r in rows if r["age_days"] >= min_age]

    # Attach the best strategy per row so the table can show it in one pass.
    for row in rows:
        case = _latest_case(db, row["product_id"], row["store_id"])
        if case and case.plans:
            plan = sorted(case.plans, key=lambda p: float(p.expected_net_recovery), reverse=True)[0]
            allocs = plan.allocations or []
            row["best_strategy"] = allocs[0]["agent"] if allocs else None
            row["strategy_type"] = plan.strategy
            row["expected_recovery"] = float(plan.expected_recovery)
            row["expected_net_recovery"] = float(plan.expected_net_recovery)
            row["guardrail_status"] = plan.guardrail_status
        else:
            row["best_strategy"] = None
            row["expected_recovery"] = None
            row["expected_net_recovery"] = None
            row["guardrail_status"] = None

    total = len(rows)
    start = (page - 1) * page_size
    return {"items": rows[start : start + page_size], "total": total, "page": page, "page_size": page_size}


def _latest_case(db: Session, product_id: str, store_id: str):
    from app.models import RecoveryCase

    return db.scalars(
        select(RecoveryCase)
        .where(RecoveryCase.product_id == uuid.UUID(str(product_id)), RecoveryCase.store_id == uuid.UUID(str(store_id)))
        .order_by(RecoveryCase.detected_at.desc())
    ).first()


@router.get("/products/{product_id}")
def product_detail(
    product_id: str,
    store: str | None = None,
    db: Session = Depends(db_session),
    _: User = Depends(current_user),
) -> dict:
    pid = parse_uuid(product_id, "product id")
    product = db.get(Product, pid)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")

    stmt = select(Inventory).where(Inventory.product_id == pid)
    if store:
        store_row = db.scalars(select(Store).where(Store.code == store)).first()
        if store_row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown store '{store}'.")
        stmt = stmt.where(Inventory.store_id == store_row.id)

    inventories = []
    for inv in db.scalars(stmt):
        store_row = inv.store
        sales = dead_stock_service.to_sale_points(
            dead_stock_service.load_sales(db, pid, inv.store_id, days=200)
        )
        forecast = demand_forecast_service.forecast_for(db, product, store_row, inv, persist=True)
        metrics = dead_stock_service.compute_metrics(
            quantity=inv.quantity,
            unit_cost=float(product.unit_cost),
            first_received_at=inv.first_received_at,
            last_sold_at=inv.last_sold_at,
            sales=sales,
            forecast_30d=forecast.forecast_30d,
            as_of=date.today(),
        )
        history = _sales_history(db, pid, inv.store_id, days=180)
        inventories.append(
            {
                "store_id": str(store_row.id),
                "store": store_row.code,
                "store_name": store_row.name,
                "quantity": inv.quantity,
                "discount_pct": float(inv.discount_pct),
                "location_code": inv.location_code,
                "first_received_at": inv.first_received_at.isoformat(),
                "last_sold_at": inv.last_sold_at.isoformat() if inv.last_sold_at else None,
                "capital_locked": metrics.capital_locked,
                "metrics": metrics.model_dump(),
                "forecast": forecast.model_dump(mode="json"),
                "sales_history": history,
                "is_recovery_candidate": dead_stock_service.is_recovery_candidate(metrics, inv.quantity),
            }
        )

    return {
        "product": {
            "id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "category": product.category.name,
            "unit_cost": float(product.unit_cost),
            "list_price": float(product.list_price),
            "b2b_floor_pct": float(product.b2b_floor_pct),
            "dimensions_cm": product.dimensions_cm,
        },
        "inventory": inventories,
    }


@router.get("/products/{product_id}/forecast")
def product_forecast(
    product_id: str,
    store: str,
    db: Session = Depends(db_session),
    _: User = Depends(current_user),
) -> dict:
    pid = parse_uuid(product_id, "product id")
    product = db.get(Product, pid)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
    store_row = db.scalars(select(Store).where(Store.code == store)).first()
    if store_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown store '{store}'.")
    inv = db.scalars(
        select(Inventory).where(Inventory.product_id == pid, Inventory.store_id == store_row.id)
    ).first()
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No inventory for that product at that store.")
    forecast = demand_forecast_service.forecast_for(db, product, store_row, inv, persist=True)
    return forecast.model_dump(mode="json")


@router.get("/products/{product_id}/recovery-options")
def recovery_options(
    product_id: str,
    store: str,
    db: Session = Depends(db_session),
    _: User = Depends(current_user),
) -> dict:
    pid = parse_uuid(product_id, "product id")
    product = db.get(Product, pid)
    store_row = db.scalars(select(Store).where(Store.code == store)).first()
    if product is None or store_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown product or store.")
    inv = db.scalars(
        select(Inventory).where(Inventory.product_id == pid, Inventory.store_id == store_row.id)
    ).first()
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No inventory for that product at that store.")
    ctx = recovery_engine.build_context(db, product, store_row, inv)
    results = recovery_engine.run_agents(ctx)
    for result in results:
        result.expected_net_recovery = recovery_engine.compute_net_recovery(result, ctx.policy)
    return {
        "product_id": str(product.id),
        "store": store_row.code,
        "available_units": ctx.available_units,
        "metrics": ctx.metrics.model_dump(),
        "forecast": ctx.forecast.model_dump(mode="json"),
        "agent_results": [r.model_dump(mode="json") for r in results],
    }


def _sales_history(db: Session, product_id: uuid.UUID, store_id: uuid.UUID, days: int = 180) -> list[dict]:
    from datetime import timedelta

    since = date.today() - timedelta(days=days)
    rows = db.scalars(
        select(Sale)
        .where(Sale.product_id == product_id, Sale.store_id == store_id, Sale.sold_on >= since)
        .order_by(Sale.sold_on)
    )
    return [
        {
            "date": s.sold_on.isoformat(),
            "quantity": s.quantity,
            "unit_price": float(s.unit_price),
            "is_promotion": s.is_promotion,
        }
        for s in rows
    ]
