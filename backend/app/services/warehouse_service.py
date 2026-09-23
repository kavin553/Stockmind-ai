"""WAREHOUSE LAYOUT SERVICE — spatial view of real inventory (a service, not an agent).

Groups inventory rows by their physical ``location_code`` so the 3D digital twin can colour
racks from **actual risk data**. Nothing here is hardcoded: a location with no usable rows is
reported as ``insufficient_data`` rather than being assigned a fabricated risk colour.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Inventory, Store
from app.services import dead_stock_service, demand_forecast_service

RACK_PATTERN = re.compile(r"^(?P<rack>[A-Za-z]+\d+)(?:[-_](?P<shelf>[A-Za-z]*\d+))?$")


def parse_location(location_code: str | None) -> tuple[str, str]:
    """Split a location like ``R1-S2`` into ``("R1", "S2")``.

    Unparseable or empty codes land in an explicit "UNASSIGNED" rack so they are visible
    instead of silently dropped.
    """
    if not location_code:
        return "UNASSIGNED", "UNASSIGNED"
    match = RACK_PATTERN.match(location_code.strip().upper())
    if not match:
        return "UNASSIGNED", location_code.strip().upper()
    return match.group("rack"), (match.group("shelf") or "S1")


def _weight(value: dict) -> float:
    """Value used to weight a risk average — item rows carry ``capital_locked``, shelf rows
    carry ``total_value``."""
    return max(float(value.get("capital_locked", value.get("total_value", 0.0)) or 0.0), 0.0)


def _weighted_risk(rows: list[dict]) -> float:
    total_weight = sum(_weight(row) for row in rows)
    if total_weight <= 0:
        return 0.0
    return round(sum(row["risk_score"] * _weight(row) for row in rows) / total_weight, 4)


def warehouse_layout(db: Session, store_code: str | None = None) -> dict:
    stmt = select(Inventory).join(Store, Store.id == Inventory.store_id)
    store = None
    if store_code:
        store = db.scalars(select(Store).where(Store.code == store_code)).first()
        if store is None:
            raise ValueError(f"Unknown store '{store_code}'.")
        stmt = stmt.where(Inventory.store_id == store.id)
    else:
        store = db.scalars(select(Store)).first()

    if store is None:
        return {"store": None, "racks": [], "generated_at": date.today().isoformat()}

    stmt = stmt.where(Inventory.store_id == store.id)
    shelves: dict[str, list[dict]] = defaultdict(list)
    today = date.today()

    for inv in db.scalars(stmt):
        product = inv.product
        sales = dead_stock_service.to_sale_points(
            dead_stock_service.load_sales(db, inv.product_id, inv.store_id, days=200)
        )
        forecast_30d = demand_forecast_service.cached_forecast_30d(db, inv.product_id, inv.store_id)
        metrics = dead_stock_service.compute_metrics(
            quantity=inv.quantity,
            unit_cost=float(product.unit_cost),
            first_received_at=inv.first_received_at,
            last_sold_at=inv.last_sold_at,
            sales=sales,
            forecast_30d=forecast_30d,
            as_of=today,
        )
        shelves[inv.location_code or "UNASSIGNED"].append(
            {
                "product_id": str(product.id),
                "store_id": str(inv.store_id),
                "sku": product.sku,
                "name": product.name,
                "quantity": inv.quantity,
                "unit_cost": float(product.unit_cost),
                "capital_locked": metrics.capital_locked,
                "risk_score": metrics.risk_score,
                "risk_band": metrics.risk_band,
                "age_days": metrics.age_days,
                "days_since_sale": metrics.days_since_sale,
                "forecast_30d": forecast_30d,
                "is_recovery_candidate": dead_stock_service.is_recovery_candidate(metrics, inv.quantity),
            }
        )

    rack_map: dict[str, list[dict]] = defaultdict(list)
    for location_code in sorted(shelves):
        rack, shelf = parse_location(location_code)
        rack_map[rack].append(
            {
                "location_code": location_code,
                "shelf": shelf,
                "unit_count": len(shelves[location_code]),
                "total_units": sum(item["quantity"] for item in shelves[location_code]),
                "total_value": round(sum(item["capital_locked"] for item in shelves[location_code]), 2),
                "risk_score": _weighted_risk(shelves[location_code]),
                "risk_band": dead_stock_service.risk_band(_weighted_risk(shelves[location_code])),
                "recovery_candidates": sum(1 for item in shelves[location_code] if item["is_recovery_candidate"]),
                "items": shelves[location_code],
            }
        )

    racks = []
    for rack_id in sorted(rack_map):
        shelf_list = sorted(rack_map[rack_id], key=lambda shelf: shelf["shelf"])
        racks.append(
            {
                "id": rack_id,
                "shelf_count": len(shelf_list),
                "total_units": sum(shelf["total_units"] for shelf in shelf_list),
                "total_value": round(sum(shelf["total_value"] for shelf in shelf_list), 2),
                "risk_score": _weighted_risk(shelf_list),
                "risk_band": dead_stock_service.risk_band(_weighted_risk(shelf_list)),
                "shelves": shelf_list,
            }
        )

    return {
        "store": {
            "id": str(store.id),
            "code": store.code,
            "name": store.name,
            "city": store.city,
        },
        "racks": racks,
        "generated_at": today.isoformat(),
    }


def location_detail(db: Session, store_code: str, location_code: str) -> dict:
    """Inventory actually held at one location — what the click handler shows."""
    layout = warehouse_layout(db, store_code)
    for rack in layout["racks"]:
        for shelf in rack["shelves"]:
            if shelf["location_code"] == location_code:
                return {
                    "store": layout["store"],
                    "rack": rack["id"],
                    "location": shelf,
                    "insufficient_data": shelf["unit_count"] == 0,
                }
    return {
        "store": layout["store"],
        "rack": parse_location(location_code)[0],
        "location": None,
        "insufficient_data": True,
    }
