from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session, parse_uuid
from app.models import B2BBuyer, Inventory, Product, Sale, Store, User
from app.services import data_ingest_service, dead_stock_service

router = APIRouter(tags=["network"])


@router.get("/stores")
def stores(db: Session = Depends(db_session), _: User = Depends(current_user)) -> dict:
    items = []
    for store in db.scalars(select(Store).where(Store.is_active.is_(True))):
        inventory_value = 0.0
        dead_value = 0.0
        units = 0
        demand = 0.0
        for inv in db.scalars(select(Inventory).where(Inventory.store_id == store.id)):
            value = inv.quantity * float(inv.product.unit_cost)
            inventory_value += value
            units += inv.quantity
            sales = dead_stock_service.to_sale_points(
                dead_stock_service.load_sales(db, inv.product_id, inv.store_id, days=200)
            )
            m = dead_stock_service.compute_metrics(
                quantity=inv.quantity,
                unit_cost=float(inv.product.unit_cost),
                first_received_at=inv.first_received_at,
                last_sold_at=inv.last_sold_at,
                sales=sales,
                forecast_30d=0.0,
                as_of=date.today(),
            )
            if dead_stock_service.is_recovery_candidate(m, inv.quantity):
                dead_value += value
            demand += m.sales_velocity_30d * 30
        items.append(
            {
                "id": str(store.id),
                "code": store.code,
                "name": store.name,
                "city": store.city,
                "region": store.region,
                "lat": float(store.lat) if store.lat is not None else None,
                "lon": float(store.lon) if store.lon is not None else None,
                "inventory_value": round(inventory_value, 2),
                "dead_stock_value": round(dead_value, 2),
                "units": units,
                "demand_30d": round(demand, 2),
            }
        )
    return {"items": items}


@router.get("/stores/transfer-opportunities")
def transfer_opportunities(db: Session = Depends(db_session), _: User = Depends(current_user)) -> dict:
    """Live source→destination candidates computed by the Inter-Store Swap Agent."""
    from app.services import recovery_engine

    opportunities = []
    for inv in db.scalars(select(Inventory).where(Inventory.quantity > 0).limit(400)):
        product = inv.product
        store = inv.store
        sales = dead_stock_service.to_sale_points(
            dead_stock_service.load_sales(db, product.id, inv.store_id, days=200)
        )
        from app.services.demand_forecast_service import cached_forecast_30d

        m = dead_stock_service.compute_metrics(
            quantity=inv.quantity,
            unit_cost=float(product.unit_cost),
            first_received_at=inv.first_received_at,
            last_sold_at=inv.last_sold_at,
            sales=sales,
            forecast_30d=cached_forecast_30d(db, product.id, inv.store_id),
            as_of=date.today(),
        )
        if not dead_stock_service.is_recovery_candidate(m, inv.quantity):
            continue
        peers = recovery_engine._peer_stores(db, product, store.id, store)
        best = None
        for peer in peers:
            headroom = max(0.0, peer.forecast_30d - peer.quantity_on_hand)
            if headroom <= 0:
                continue
            qty = min(float(inv.quantity), headroom, 500)
            cost = qty * (12.0 + 1.6 * peer.distance_km)
            recovered = qty * float(product.list_price) * (1 - peer.current_discount_pct)
            if recovered - cost <= 0:
                continue
            candidate = {
                "product_id": str(product.id),
                "sku": product.sku,
                "name": product.name,
                "source_store": store.code,
                "destination_store": peer.store.code,
                "destination_city": peer.store.city,
                "distance_km": peer.distance_km,
                "quantity": round(qty),
                "transfer_cost": round(cost, 2),
                "expected_recovery": round(recovered, 2),
                "net": round(recovered - cost, 2),
            }
            if best is None or candidate["net"] > best["net"]:
                best = candidate
        if best:
            opportunities.append(best)
    opportunities.sort(key=lambda o: o["net"], reverse=True)
    return {"items": opportunities[:100]}


@router.get("/stores/by-id/{store_id}")
def store_detail(store_id: str, db: Session = Depends(db_session), _: User = Depends(current_user)) -> dict:
    store = db.get(Store, parse_uuid(store_id, "store id"))
    if store is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Store not found.")
    inventory = []
    for inv in db.scalars(select(Inventory).where(Inventory.store_id == store.id)):
        inventory.append(
            {
                "sku": inv.product.sku,
                "name": inv.product.name,
                "quantity": inv.quantity,
                "location_code": inv.location_code,
                "value": round(inv.quantity * float(inv.product.unit_cost), 2),
            }
        )
    return {
        "id": str(store.id),
        "code": store.code,
        "name": store.name,
        "city": store.city,
        "region": store.region,
        "inventory": inventory,
    }


@router.get("/b2b-buyers")
def b2b_buyers(db: Session = Depends(db_session), _: User = Depends(current_user)) -> dict:
    buyers = list(db.scalars(select(B2BBuyer).where(B2BBuyer.is_active.is_(True))))
    inventory_categories: dict[str, float] = {}
    for inv in db.scalars(select(Inventory).join(Product, Product.id == Inventory.product_id).where(Inventory.quantity > 0)):
        category = inv.product.category.name
        inventory_categories[category] = inventory_categories.get(category, 0.0) + (
            inv.quantity * float(inv.product.unit_cost)
        )
    items = []
    for buyer in buyers:
        matched_value = sum(inventory_categories.get(c, 0.0) for c in (buyer.required_categories or []))
        items.append(
            {
                "id": str(buyer.id),
                "business_name": buyer.business_name,
                "required_categories": buyer.required_categories,
                "location_city": buyer.location_city,
                "required_quantity": buyer.required_quantity,
                "maximum_budget": float(buyer.maximum_budget),
                "preferred_unit_price": float(buyer.preferred_unit_price),
                "reliability_score": float(buyer.reliability_score),
                "matched_dead_stock_value": round(matched_value, 2),
            }
        )
    items.sort(key=lambda b: b["matched_dead_stock_value"], reverse=True)
    return {"items": items}


@router.post("/import/csv")
async def import_csv(
    file: UploadFile = File(...),
    kind: str = Form(...),
    db: Session = Depends(db_session),
    user: User = Depends(current_user),
) -> dict:
    if kind not in data_ingest_service.SUPPORTED_KINDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"kind must be one of: {', '.join(data_ingest_service.SUPPORTED_KINDS)}",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Uploaded file is empty.")
    try:
        return data_ingest_service.import_csv(db, kind, content)
    except data_ingest_service.RowError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
