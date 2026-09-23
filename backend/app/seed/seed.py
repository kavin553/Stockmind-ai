"""Deterministic demo seed.

Creates 3 stores, 12 categories, 250+ products, 12 months of sales, inventory, B2B buyers,
users and settings — with **intentional scenarios** so the demo always has something to show:

1. dead stock best cleared by discount,
2. dead stock best cleared by an inter-store transfer,
3. dead stock best cleared by a Buy-A-Get-B bundle,
4. dead stock best cleared by a B2B bulk sale,
5. dead stock where no strong recovery option exists,
6. a low-stock fast seller that must **never** be flagged as dead stock.

The seed is idempotent: natural keys are upserted and previously seeded sales are replaced,
so running it twice cannot create uncontrolled duplicates.

    python -m app.seed.seed [--reset] [--skip-forecast]
"""
from __future__ import annotations

import argparse
import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import policy
from app.database import SessionLocal
from app.models import (
    B2BBuyer,
    Category,
    Inventory,
    Product,
    Sale,
    Setting,
    Store,
    User,
)

SEED_VERSION = "2024.1"
RNG_SEED = 20240517
TODAY = date.today()
HISTORY_DAYS = 365

CATEGORIES = [
    ("Apparel", 1.35),
    ("Footwear", 1.20),
    ("Accessories", 1.45),
    ("Home & Living", 1.05),
    ("Kitchen", 1.00),
    ("Electronics", 1.10),
    ("Beauty", 1.25),
    ("Toys", 1.30),
    ("Stationery", 0.95),
    ("Sports", 1.15),
    ("Grocery", 0.85),
    ("Furniture", 0.75),
]

# Affinity map used by the Buy-A-Get-B agent. Values are 0..1.
AFFINITY = {
    "Apparel": {"Accessories": 0.82, "Footwear": 0.61, "Beauty": 0.40},
    "Accessories": {"Apparel": 0.80, "Beauty": 0.55, "Footwear": 0.44},
    "Footwear": {"Apparel": 0.62, "Sports": 0.58, "Accessories": 0.47},
    "Home & Living": {"Kitchen": 0.71, "Furniture": 0.52, "Grocery": 0.30},
    "Kitchen": {"Home & Living": 0.69, "Grocery": 0.50, "Electronics": 0.33},
    "Electronics": {"Accessories": 0.49, "Home & Living": 0.41, "Toys": 0.36},
    "Beauty": {"Accessories": 0.60, "Apparel": 0.38, "Grocery": 0.34},
    "Toys": {"Stationery": 0.57, "Sports": 0.42, "Electronics": 0.35},
    "Stationery": {"Toys": 0.55, "Home & Living": 0.33, "Electronics": 0.31},
    "Sports": {"Footwear": 0.60, "Apparel": 0.45, "Toys": 0.39},
    "Grocery": {"Kitchen": 0.52, "Home & Living": 0.31, "Beauty": 0.28},
    "Furniture": {"Home & Living": 0.50},  # deliberately sparse
}

STORES = [
    ("STR-BLR-01", "Indiranagar Flagship", "Bengaluru", "Karnataka", 12.9719, 77.6412),
    ("STR-BLR-02", "Whitefield Mall", "Bengaluru", "Karnataka", 12.9698, 77.7500),
    ("STR-HYD-01", "Gachibowli Hub", "Hyderabad", "Telangana", 17.4401, 78.3489),
]

BUYERS = [
    ("BulkMart Wholesale", ["Apparel", "Accessories"], "Bengaluru", 12.9716, 77.5946, 100, 320000, 380, 0.86),
    ("Deccan Distributors", ["Footwear", "Sports"], "Hyderabad", 17.3850, 78.4867, 80, 260000, 520, 0.78),
    ("HomeStyle Traders", ["Home & Living", "Kitchen"], "Bengaluru", 12.9352, 77.6245, 60, 210000, 640, 0.82),
    ("GlowUp Retail", ["Beauty", "Accessories"], "Chennai", 13.0827, 80.2707, 120, 180000, 240, 0.71),
    ("PlayBox Toys", ["Toys", "Stationery"], "Hyderabad", 17.4239, 78.4738, 150, 240000, 300, 0.80),
    ("Metro Bazaar", ["Grocery", "Home & Living"], "Bengaluru", 12.9121, 77.6446, 200, 150000, 180, 0.65),
    ("TechRecycle Ltd", ["Electronics"], "Pune", 18.5204, 73.8567, 50, 400000, 1800, 0.74),
]

# Profiles drive the intentional scenarios.
PROFILE_CYCLE = [
    "discount_dead",
    "transfer_dead",
    "bundle_dead",
    "b2b_dead",
    "no_recovery",
    "steady",
    "seasonal",
    "slow",
    "steady",
    "low_stock_fast",
]

CATEGORY_OF_PROFILE = {
    "discount_dead": ["Apparel", "Beauty", "Grocery"],
    "transfer_dead": ["Footwear", "Sports", "Toys"],
    "bundle_dead": ["Accessories", "Stationery", "Kitchen"],
    "b2b_dead": ["Apparel", "Home & Living", "Beauty"],
    "no_recovery": ["Furniture"],
    "steady": None,
    "seasonal": None,
    "slow": None,
    "low_stock_fast": None,
}


def _season_factor(day_of_year: int) -> float:
    return 1.0 + 0.22 * float(np.sin(2 * np.pi * (day_of_year - 40) / 365.0))


def _store_multiplier(profile: str, store_index: int, rng: random.Random) -> float:
    if profile == "transfer_dead":
        # source store (index 2) is weak, destinations (0, 1) are strong
        return {0: 1.6, 1: 2.4, 2: 0.02}.get(store_index, 1.0)
    if profile == "b2b_dead":
        return {0: 0.02, 1: 0.01, 2: 0.01}.get(store_index, 0.02)
    if profile == "no_recovery":
        return 0.0
    return round(rng.uniform(0.6, 1.4), 3)


def _base_daily(profile: str, rng: random.Random) -> float:
    return {
        "discount_dead": rng.uniform(0.05, 0.25),
        "transfer_dead": rng.uniform(0.9, 2.4),  # strong at destination stores
        "bundle_dead": rng.uniform(0.02, 0.12),
        "b2b_dead": rng.uniform(0.005, 0.03),
        "no_recovery": 0.0,
        "steady": rng.uniform(1.5, 4.5),
        "seasonal": rng.uniform(0.8, 2.6),
        "slow": rng.uniform(0.15, 0.6),
        "low_stock_fast": rng.uniform(2.5, 6.0),
    }[profile]


def _age_days(profile: str, rng: random.Random) -> int:
    return {
        "discount_dead": rng.randint(75, 150),
        "transfer_dead": rng.randint(70, 140),
        "bundle_dead": rng.randint(70, 160),
        "b2b_dead": rng.randint(90, 220),
        "no_recovery": rng.randint(80, 200),
        "steady": rng.randint(5, 70),
        "seasonal": rng.randint(10, 90),
        "slow": rng.randint(30, 180),
        "low_stock_fast": rng.randint(20, 60),
    }[profile]


def _quantity(profile: str, rng: random.Random) -> int:
    return {
        "discount_dead": rng.randint(60, 180),
        "transfer_dead": rng.randint(40, 140),
        "bundle_dead": rng.randint(50, 160),
        "b2b_dead": rng.randint(300, 900),
        "no_recovery": rng.randint(25, 60),
        "steady": rng.randint(15, 90),
        "seasonal": rng.randint(20, 110),
        "slow": rng.randint(20, 120),
        "low_stock_fast": rng.randint(1, 4),
    }[profile]


def _sales_cutoff_days(profile: str, rng: random.Random) -> int:
    """How many days before today the SKU stopped selling (for aged profiles)."""
    return {
        "discount_dead": rng.randint(25, 60),
        "transfer_dead": rng.randint(20, 55),
        "bundle_dead": rng.randint(25, 70),
        "b2b_dead": rng.randint(40, 110),
        "no_recovery": rng.randint(35, 95),
        "slow": rng.randint(5, 40),
        "steady": 0,
        "seasonal": 0,
        "low_stock_fast": 0,
    }[profile]


def seed(session: Session, *, reset: bool = False, run_forecasts: bool = True) -> dict:
    rng = random.Random(RNG_SEED)
    np_rng = np.random.default_rng(RNG_SEED)
    summary: dict = {}

    if reset:
        _reset(session)

    # --- settings -----------------------------------------------------------
    for key, value in {
        "AGING_DAYS": policy.aging_days,
        "NO_SALE_DAYS": policy.no_sale_days,
        "EXCESS_STOCK_MULTIPLIER": policy.excess_stock_multiplier,
        "MAX_AUTONOMOUS_DISCOUNT": policy.max_autonomous_discount,
        "MIN_MARGIN_PCT": policy.min_margin_pct,
        "B2B_PRICE_FLOOR_PCT": policy.b2b_price_floor_pct,
        "TRANSFER_MAX_UNITS": policy.transfer_max_units,
        "SEED_VERSION": SEED_VERSION,
    }.items():
        row = session.get(Setting, key)
        if row is None:
            session.add(Setting(key=key, value={"value": value}))
        else:
            row.value = {"value": value}
    session.flush()

    # --- stores -------------------------------------------------------------
    stores: list[Store] = []
    for code, name, city, region, lat, lon in STORES:
        store = session.scalars(select(Store).where(Store.code == code)).first()
        if store is None:
            store = Store(code=code, name=name, city=city, region=region, lat=Decimal(str(lat)), lon=Decimal(str(lon)))
            session.add(store)
        stores.append(store)
    session.flush()

    # --- categories ---------------------------------------------------------
    categories: dict[str, Category] = {}
    for name, elasticity in CATEGORIES:
        category = session.scalars(select(Category).where(Category.name == name)).first()
        if category is None:
            category = Category(
                name=name,
                elasticity=Decimal(str(elasticity)),
                co_purchase_affinity=AFFINITY.get(name, {}),
            )
            session.add(category)
        else:
            category.elasticity = Decimal(str(elasticity))
            category.co_purchase_affinity = AFFINITY.get(name, {})
        categories[name] = category
    session.flush()

    # --- products -----------------------------------------------------------
    product_count = 252
    products: list[tuple[Product, str, list[float]]] = []
    existing_skus = set(session.scalars(select(Product.sku)))
    for index in range(product_count):
        profile = PROFILE_CYCLE[index % len(PROFILE_CYCLE)]
        allowed = CATEGORY_OF_PROFILE.get(profile) or [c[0] for c in CATEGORIES]
        category_name = allowed[index % len(allowed)]
        category = categories[category_name]
        sku = f"SKU-{1000 + index}"

        if profile == "no_recovery":
            unit_cost = Decimal(str(round(rng.uniform(4200, 7800), 2)))
            markup = rng.uniform(1.35, 1.6)
        elif profile == "b2b_dead":
            unit_cost = Decimal(str(round(rng.uniform(180, 460), 2)))
            markup = rng.uniform(2.2, 3.0)
        else:
            unit_cost = Decimal(str(round(rng.uniform(120, 1400), 2)))
            markup = rng.uniform(1.7, 2.6)
        list_price = Decimal(str(round(float(unit_cost) * markup, 2)))

        product = session.scalars(select(Product).where(Product.sku == sku)).first()
        if product is None:
            product = Product(
                sku=sku,
                name=f"{category_name} {profile.replace('_', ' ').title()} {1000 + index}",
                category_id=category.id,
                unit_cost=unit_cost,
                list_price=list_price,
                b2b_floor_pct=Decimal("0.80"),
                dimensions_cm={
                    "l": round(rng.uniform(8, 60), 1),
                    "w": round(rng.uniform(5, 45), 1),
                    "h": round(rng.uniform(2, 35), 1),
                },
            )
            session.add(product)
        else:
            product.name = f"{category_name} {profile.replace('_', ' ').title()} {1000 + index}"
            product.category_id = category.id
            product.unit_cost = unit_cost
            product.list_price = list_price
        session.flush()

        base = _base_daily(profile, rng)
        multipliers = [_store_multiplier(profile, i, rng) for i in range(len(stores))]
        products.append((product, profile, [base * m for m in multipliers]))

    session.flush()
    summary["products"] = len(products)

    # --- clear previously seeded sales/inventory ---------------------------
    product_ids = [p.id for p, _, _ in products]
    session.execute(delete(Sale).where(Sale.product_id.in_(product_ids)))
    session.execute(delete(Inventory).where(Inventory.product_id.in_(product_ids)))
    session.flush()

    # --- sales + inventory --------------------------------------------------
    sale_rows: list[dict] = []
    inventory_rows: list[Inventory] = []
    start_day = TODAY - timedelta(days=HISTORY_DAYS)
    for product, profile, per_store in products:
        cutoff_days = _sales_cutoff_days(profile, rng)
        age = _age_days(profile, rng)
        quantity = _quantity(profile, rng)
        carried = [True, rng.random() < 0.8, rng.random() < 0.6]
        if profile in ("transfer_dead", "b2b_dead", "no_recovery"):
            carried = [True, True, True]
        if profile == "low_stock_fast":
            carried = [True, rng.random() < 0.7, rng.random() < 0.5]

        for store_index, store in enumerate(stores):
            if not carried[store_index]:
                continue
            base = per_store[store_index]
            last_sold: date | None = None
            if base > 0:
                for day_offset in range(HISTORY_DAYS):
                    day = start_day + timedelta(days=day_offset)
                    days_ago = (TODAY - day).days
                    if profile in ("discount_dead", "transfer_dead", "bundle_dead", "b2b_dead", "no_recovery"):
                        if days_ago <= cutoff_days:
                            continue
                        # fading demand before the cutoff
                        decay = max(0.15, 1.0 - (HISTORY_DAYS - days_ago) / HISTORY_DAYS)
                    else:
                        decay = 1.0
                    seasonal = _season_factor(day.timetuple().tm_yday) if profile == "seasonal" else 1.0
                    lam = max(0.0, base * seasonal * decay)
                    if lam <= 0:
                        continue
                    count = int(np_rng.poisson(lam))
                    if count <= 0:
                        continue
                    is_promo = rng.random() < 0.08
                    price = float(product.list_price) * (0.85 if is_promo else 1.0)
                    sale_rows.append(
                        {
                            "product_id": product.id,
                            "store_id": store.id,
                            "sold_on": day,
                            "quantity": count,
                            "unit_price": Decimal(str(round(price, 2))),
                            "unit_cost": product.unit_cost,
                            "is_promotion": is_promo,
                        }
                    )
                    last_sold = day

            store_quantity = quantity
            if profile == "transfer_dead":
                store_quantity = quantity if store_index == 2 else rng.randint(3, 18)
            elif profile == "b2b_dead":
                store_quantity = quantity if store_index == 0 else int(quantity * 0.1)
            elif profile == "low_stock_fast":
                store_quantity = rng.randint(1, 3)

            received = TODAY - timedelta(days=age)
            inventory_rows.append(
                Inventory(
                    product_id=product.id,
                    store_id=store.id,
                    quantity=store_quantity,
                    discount_pct=Decimal("0"),
                    first_received_at=received,
                    last_sold_at=last_sold,
                    location_code=f"R{rng.randint(1, 6)}-S{rng.randint(1, 4)}",
                    updated_at=TODAY,
                )
            )

    _bulk_insert_sales(session, sale_rows)
    session.add_all(inventory_rows)
    session.flush()
    summary["sales"] = len(sale_rows)
    summary["inventory_rows"] = len(inventory_rows)

    # --- B2B buyers ---------------------------------------------------------
    for name, cats, city, lat, lon, qty, budget, price, reliability in BUYERS:
        buyer = session.scalars(select(B2BBuyer).where(B2BBuyer.business_name == name)).first()
        if buyer is None:
            buyer = B2BBuyer(business_name=name)
            session.add(buyer)
        buyer.required_categories = cats
        buyer.location_city = city
        buyer.lat = Decimal(str(lat))
        buyer.lon = Decimal(str(lon))
        buyer.required_quantity = qty
        buyer.maximum_budget = Decimal(str(budget))
        buyer.preferred_unit_price = Decimal(str(price))
        buyer.reliability_score = Decimal(str(reliability))
        buyer.is_active = True
    session.flush()
    summary["buyers"] = len(BUYERS)

    # --- users --------------------------------------------------------------
    demo_users = [
        ("manager@stockmind.demo", "Priya Nair", "store_manager", stores[0].id),
        ("inventory@stockmind.demo", "Arun Kumar", "inventory_staff", stores[0].id),
    ]
    for email, full_name, role, store_id in demo_users:
        user = session.scalars(select(User).where(User.email == email)).first()
        if user is None:
            user = User(email=email, full_name=full_name, password_hash=hash_password("demo1234"), role=role, store_id=store_id)
            session.add(user)
        else:
            user.full_name = full_name
            user.role = role
            user.store_id = store_id
            user.password_hash = hash_password("demo1234")
    session.flush()
    summary["users"] = len(demo_users)

    session.commit()

    if run_forecasts:
        summary["forecasts"] = _run_forecasts(session)

    return summary


def _bulk_insert_sales(session: Session, rows: list[dict], chunk: int = 4000) -> None:
    for start in range(0, len(rows), chunk):
        session.execute(insert(Sale), rows[start : start + chunk])


def _run_forecasts(session: Session) -> int:
    from app.services import demand_forecast_service

    count = 0
    rows = list(session.scalars(select(Inventory)))
    for inventory in rows:
        product = inventory.product
        store = inventory.store
        demand_forecast_service.forecast_for(session, product, store, inventory, persist=True)
        count += 1
        if count % 50 == 0:
            session.commit()
    session.commit()
    return count


def _reset(session: Session) -> None:
    for model in (Sale, Inventory, Product, Category, Store, B2BBuyer, User, Setting):
        session.execute(delete(model))
    session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the StockMind AI demo dataset.")
    parser.add_argument("--reset", action="store_true", help="delete existing rows first")
    parser.add_argument("--skip-forecast", action="store_true", help="skip the forecast warm-up")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        summary = seed(session, reset=args.reset, run_forecasts=not args.skip_forecast)
        print("Seed complete:")
        for key, value in summary.items():
            print(f"  {key}: {value}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
