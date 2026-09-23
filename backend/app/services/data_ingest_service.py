"""DATA INGEST SERVICE — CSV validation and upsert.

Validation is server-side and pure (:func:`validate_rows`), so it is unit-testable without a
database. Rejected rows are reported individually; valid rows are still imported.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Inventory, Product, Sale, Store

SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9\-]{2,31}$")
SUPPORTED_KINDS = ("products", "inventory", "sales")


class RowError(ValueError):
    pass


def parse_date(value: str) -> date:
    value = (value or "").strip()
    if not value:
        raise RowError("missing date")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise RowError(f"unparseable date '{value}'")


def parse_decimal(value: str, field: str, *, minimum: float | None = None, allow_zero: bool = True) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        raise RowError(f"{field} is not a number") from None
    if number < 0:
        raise RowError(f"{field} cannot be negative")
    if minimum is not None and number < minimum:
        raise RowError(f"{field} must be at least {minimum}")
    if not allow_zero and number == 0:
        raise RowError(f"{field} must be greater than zero")
    return number


def parse_int(value: str, field: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        raise RowError(f"{field} is not an integer") from None
    if number < minimum:
        raise RowError(f"{field} cannot be below {minimum}")
    if maximum is not None and number > maximum:
        raise RowError(f"{field} cannot exceed {maximum}")
    return number


def validate_sku(value: str) -> str:
    sku = (value or "").strip().upper()
    if not SKU_PATTERN.match(sku):
        raise RowError(f"malformed SKU '{value}'")
    return sku


def validate_rows(
    kind: str,
    rows: list[dict],
    *,
    known_skus: set[str],
    known_stores: set[str],
    known_categories: set[str],
    today: date | None = None,
) -> tuple[list[dict], list[dict]]:
    """Return ``(accepted, rejected)``. Every rejection carries row number and reason."""
    if kind not in SUPPORTED_KINDS:
        raise RowError(f"unsupported import kind '{kind}'")
    today = today or date.today()
    accepted: list[dict] = []
    rejected: list[dict] = []
    seen: set[tuple] = set()

    for index, raw in enumerate(rows, start=2):  # row 1 is the header
        try:
            if kind == "products":
                sku = validate_sku(raw.get("sku", ""))
                name = (raw.get("name") or "").strip()
                category = (raw.get("category") or "").strip()
                if not name:
                    raise RowError("name is required")
                if category and category not in known_categories:
                    raise RowError(f"unknown category '{category}'")
                cost = parse_decimal(raw.get("unit_cost"), "unit_cost", allow_zero=False)
                price = parse_decimal(raw.get("list_price"), "list_price", allow_zero=False)
                if cost > price * 2:
                    raise RowError("unit_cost is more than 2x list_price")
                record = {"sku": sku, "name": name, "category": category, "unit_cost": cost, "list_price": price}
            elif kind == "inventory":
                sku = validate_sku(raw.get("sku", ""))
                store = (raw.get("store_code") or "").strip()
                if sku not in known_skus:
                    raise RowError(f"unknown SKU '{sku}'")
                if store not in known_stores:
                    raise RowError(f"unknown store '{store}'")
                quantity = parse_int(raw.get("quantity"), "quantity", minimum=0)
                received = parse_date(raw.get("first_received_at") or raw.get("received_at") or "")
                if received > today:
                    raise RowError("first_received_at is in the future")
                last_sold_raw = (raw.get("last_sold_at") or "").strip()
                last_sold = parse_date(last_sold_raw) if last_sold_raw else None
                if last_sold and last_sold > today:
                    raise RowError("last_sold_at is in the future")
                record = {
                    "sku": sku,
                    "store_code": store,
                    "quantity": quantity,
                    "first_received_at": received,
                    "last_sold_at": last_sold,
                    "location_code": (raw.get("location_code") or "UNASSIGNED").strip() or "UNASSIGNED",
                }
            else:  # sales
                sku = validate_sku(raw.get("sku", ""))
                store = (raw.get("store_code") or "").strip()
                if sku not in known_skus:
                    raise RowError(f"unknown SKU '{sku}'")
                if store not in known_stores:
                    raise RowError(f"unknown store '{store}'")
                sold_on = parse_date(raw.get("sold_on") or raw.get("date") or "")
                if sold_on > today:
                    raise RowError("sale date is in the future")
                quantity = parse_int(raw.get("quantity"), "quantity", minimum=1, maximum=100000)
                price = parse_decimal(raw.get("unit_price"), "unit_price", allow_zero=False)
                record = {"sku": sku, "store_code": store, "sold_on": sold_on, "quantity": quantity, "unit_price": price}

            key = _dedup_key(kind, record)
            if key in seen:
                raise RowError("duplicate row")
            seen.add(key)
            accepted.append(record)
        except RowError as exc:
            rejected.append({"row": index, "reason": str(exc), "raw": raw})

    return accepted, rejected


def _dedup_key(kind: str, record: dict) -> tuple:
    if kind == "products":
        return (kind, record["sku"])
    if kind == "inventory":
        return (kind, record["sku"], record["store_code"], record["first_received_at"])
    return (kind, record["sku"], record["store_code"], record["sold_on"], record["quantity"], record["unit_price"])


def read_csv(content: bytes | str) -> list[dict]:
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise RowError("CSV has no header row")
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]


def import_csv(db: Session, kind: str, content: bytes | str) -> dict:
    """Validate then upsert. Returns accepted/rejected counts and per-row errors."""
    rows = read_csv(content)
    known_skus = set(db.scalars(select(Product.sku)))
    known_stores = set(db.scalars(select(Store.code)))
    accepted, rejected = validate_rows(
        kind, rows, known_skus=known_skus, known_stores=known_stores, known_categories=set()
    )

    created = updated = 0
    for record in accepted:
        if kind == "products":
            continue  # products must go through the category-aware path below
        if kind == "inventory":
            product = db.scalars(select(Product).where(Product.sku == record["sku"])).one()
            store = db.scalars(select(Store).where(Store.code == record["store_code"])).one()
            existing = db.scalars(
                select(Inventory).where(Inventory.product_id == product.id, Inventory.store_id == store.id)
            ).first()
            if existing:
                existing.quantity = record["quantity"]
                existing.first_received_at = record["first_received_at"]
                existing.last_sold_at = record["last_sold_at"]
                existing.location_code = record["location_code"]
                existing.updated_at = date.today()
                updated += 1
            else:
                db.add(
                    Inventory(
                        product_id=product.id,
                        store_id=store.id,
                        quantity=record["quantity"],
                        first_received_at=record["first_received_at"],
                        last_sold_at=record["last_sold_at"],
                        location_code=record["location_code"],
                        updated_at=date.today(),
                    )
                )
                created += 1
        else:
            product = db.scalars(select(Product).where(Product.sku == record["sku"])).one()
            store = db.scalars(select(Store).where(Store.code == record["store_code"])).one()
            db.add(
                Sale(
                    product_id=product.id,
                    store_id=store.id,
                    sold_on=record["sold_on"],
                    quantity=record["quantity"],
                    unit_price=Decimal(str(record["unit_price"])),
                    unit_cost=product.unit_cost,
                    is_promotion=False,
                )
            )
            created += 1

    db.commit()
    return {
        "kind": kind,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "created": created,
        "updated": updated,
        "errors": rejected[:200],
    }
