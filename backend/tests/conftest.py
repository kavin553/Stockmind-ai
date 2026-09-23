"""Shared test fixtures.

The suite runs against SQLite in-memory so it needs no Postgres. The pure business-logic
tests use hand-built :class:`RecoveryContext` objects; the API tests use a small seeded
database built here (not the full 250-product demo seed).
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    B2BBuyer,
    Base,
    Category,
    Inventory,
    Product,
    Sale,
    Store,
    User,
)
from app.schemas.domain import (  # noqa: E402
    BundleCandidate,
    BuyerSpec,
    ForecastBundle,
    InventorySpec,
    PolicySpec,
    ProductSpec,
    RecoveryContext,
    SalePoint,
    StoreDemand,
    StoreSpec,
)
from app.services import dead_stock_service  # noqa: E402

TODAY = date.today()


# --------------------------------------------------------------------------- context factory


def make_store(code: str = "STR-TEST-01", city: str = "Bengaluru", lat=12.97, lon=77.64) -> StoreSpec:
    return StoreSpec(id=uuid.uuid4(), code=code, name=f"{code} store", city=city, lat=lat, lon=lon)


def make_product(**overrides) -> ProductSpec:
    values = dict(
        id=uuid.uuid4(),
        sku="SKU-TEST-001",
        name="Test Shirt",
        category="Apparel",
        category_id=uuid.uuid4(),
        unit_cost=100.0,
        list_price=250.0,
        b2b_floor_pct=0.8,
        elasticity=1.2,
        dimensions_cm={"l": 30, "w": 20, "h": 5},
    )
    values.update(overrides)
    return ProductSpec(**values)


def declining_sales(days: int = 180, start_qty: int = 4) -> list[SalePoint]:
    """A series that dries up over time — the classic dead-stock shape."""
    sales = []
    for offset in range(0, days, 4):
        qty = max(0, int(start_qty * (1 - offset / days)))
        if qty > 0:
            sales.append(
                SalePoint(sold_on=TODAY - timedelta(days=days - offset), quantity=qty, unit_price=250.0)
            )
    return sales


def steady_sales(days: int = 180, qty: int = 3) -> list[SalePoint]:
    return [
        SalePoint(sold_on=TODAY - timedelta(days=offset), quantity=qty, unit_price=250.0)
        for offset in range(days, 0, -3)
    ]


def make_context(
    *,
    product: ProductSpec | None = None,
    store: StoreSpec | None = None,
    quantity: int = 120,
    age_days: int = 100,
    last_sold_days_ago: int | None = 60,
    forecast_30d: float = 25.0,
    forecast_7d: float = 6.0,
    forecast_60d: float = 50.0,
    forecast_confidence: float = 0.6,
    recent_sales: list[SalePoint] | None = None,
    peer_stores: list[StoreDemand] | None = None,
    bundle_candidates: list[BundleCandidate] | None = None,
    b2b_buyers: list[BuyerSpec] | None = None,
    policy: PolicySpec | None = None,
) -> RecoveryContext:
    product = product or make_product()
    store = store or make_store()
    policy = policy or PolicySpec()
    sales = recent_sales if recent_sales is not None else declining_sales()
    inventory = InventorySpec(
        quantity=quantity,
        discount_pct=0.0,
        first_received_at=TODAY - timedelta(days=age_days),
        last_sold_at=TODAY - timedelta(days=last_sold_days_ago) if last_sold_days_ago is not None else None,
        location_code="R1-S1",
    )
    forecast = ForecastBundle(
        forecast_7d=forecast_7d,
        forecast_30d=forecast_30d,
        forecast_60d=forecast_60d,
        confidence=forecast_confidence,
        method="xgboost",
        as_of=TODAY,
    )
    metrics = dead_stock_service.compute_metrics(
        quantity=quantity,
        unit_cost=product.unit_cost,
        first_received_at=inventory.first_received_at,
        last_sold_at=inventory.last_sold_at,
        sales=sales,
        forecast_30d=forecast_30d,
        as_of=TODAY,
        policy=policy,
    )
    return RecoveryContext(
        product=product,
        store=store,
        inventory=inventory,
        metrics=metrics,
        forecast=forecast,
        recent_sales=sales,
        peer_stores=peer_stores or [],
        bundle_candidates=bundle_candidates or [],
        b2b_buyers=b2b_buyers or [],
        policy=policy,
    )


def make_peer(
    code: str,
    *,
    quantity_on_hand: int = 10,
    forecast_30d: float = 90.0,
    distance_km: float = 25.0,
    discount: float = 0.0,
) -> StoreDemand:
    return StoreDemand(
        store=make_store(code=code),
        quantity_on_hand=quantity_on_hand,
        forecast_7d=forecast_30d / 4,
        forecast_30d=forecast_30d,
        forecast_confidence=0.6,
        current_discount_pct=discount,
        distance_km=distance_km,
    )


def make_bundle_candidate(
    sku: str = "SKU-ANCHOR",
    *,
    price: float = 400.0,
    cost: float = 150.0,
    forecast_30d: float = 220.0,
    affinity: float = 0.8,
    co_purchase: float = 0.5,
) -> BundleCandidate:
    return BundleCandidate(
        product=make_product(id=uuid.uuid4(), sku=sku, name=f"Anchor {sku}", unit_cost=cost, list_price=price),
        store_id=uuid.uuid4(),
        quantity_on_hand=60,
        forecast_30d=forecast_30d,
        forecast_confidence=0.7,
        current_discount_pct=0.0,
        category_affinity=affinity,
        co_purchase_rate=co_purchase,
    )


def make_buyer(
    name: str = "BulkMart",
    *,
    categories: list[str] | None = None,
    required_quantity: int = 40,
    budget: float = 500000,
    preferred_price: float = 180.0,
    lat: float = 12.97,
    lon: float = 77.64,
    reliability: float = 0.85,
) -> BuyerSpec:
    return BuyerSpec(
        id=uuid.uuid4(),
        business_name=name,
        required_categories=categories or ["Apparel"],
        location_city="Bengaluru",
        lat=lat,
        lon=lon,
        required_quantity=required_quantity,
        maximum_budget=budget,
        preferred_unit_price=preferred_price,
        reliability_score=reliability,
    )


# --------------------------------------------------------------------------- db fixtures


@pytest.fixture()
def client_with_auth(seeded_db):
    """A TestClient wired to the seeded in-memory session, plus a bearer-token header."""
    from fastapi.testclient import TestClient

    from app.api import deps
    from app.main import app

    def override():
        yield seeded_db

    app.dependency_overrides[deps.db_session] = override
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login", json={"email": "manager@stockmind.demo", "password": "demo1234"}
        )
        assert response.status_code == 200, response.text
        headers = {"Authorization": f"Bearer {response.json()['token']}"}
        yield client, headers
    app.dependency_overrides.clear()


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def seeded_db(db_session):
    """A small, hand-built dataset — not the 250-product demo seed."""
    session = db_session
    stores = [
        Store(code="STR-BLR-01", name="Indiranagar", city="Bengaluru", region="KA", lat=12.97, lon=77.64),
        Store(code="STR-BLR-02", name="Whitefield", city="Bengaluru", region="KA", lat=12.96, lon=77.75),
    ]
    categories = [
        Category(name="Apparel", elasticity=1.3, co_purchase_affinity={"Accessories": 0.8}),
        Category(name="Accessories", elasticity=1.4, co_purchase_affinity={"Apparel": 0.8}),
        Category(name="Furniture", elasticity=0.7, co_purchase_affinity={}),
    ]
    session.add_all(stores + categories)
    session.flush()

    dead = Product(
        sku="SKU-2291", name="Dead Stock Tie", category_id=categories[1].id,
        unit_cost=100, list_price=250, b2b_floor_pct=0.8, dimensions_cm={"l": 30, "w": 20, "h": 5},
    )
    anchor = Product(
        sku="SKU-118", name="Hot Seller Shirt", category_id=categories[0].id,
        unit_cost=150, list_price=400, b2b_floor_pct=0.8, dimensions_cm={"l": 30, "w": 20, "h": 5},
    )
    furniture = Product(
        sku="SKU-900", name="Aged Sofa", category_id=categories[2].id,
        unit_cost=5000, list_price=8000, b2b_floor_pct=0.8, dimensions_cm={"l": 200, "w": 90, "h": 80},
    )
    session.add_all([dead, anchor, furniture])
    session.flush()

    session.add_all(
        [
            Inventory(
                product_id=dead.id, store_id=stores[0].id, quantity=120, first_received_at=TODAY - timedelta(days=93),
                last_sold_at=TODAY - timedelta(days=61), location_code="R1-S1",
            ),
            Inventory(
                product_id=dead.id, store_id=stores[1].id, quantity=5, first_received_at=TODAY - timedelta(days=93),
                last_sold_at=TODAY - timedelta(days=5), location_code="R1-S2",
            ),
            Inventory(
                product_id=anchor.id, store_id=stores[0].id, quantity=40, first_received_at=TODAY - timedelta(days=20),
                last_sold_at=TODAY - timedelta(days=1), location_code="R2-S1",
            ),
            Inventory(
                product_id=furniture.id, store_id=stores[0].id, quantity=30, first_received_at=TODAY - timedelta(days=140),
                last_sold_at=TODAY - timedelta(days=120), location_code="R3-S1",
            ),
        ]
    )

    # Anchor sells strongly; dead item sells in the past then stops; furniture never sells.
    sales = []
    for offset in range(180, 0, -2):
        sales.append(Sale(product_id=anchor.id, store_id=stores[0].id, sold_on=TODAY - timedelta(days=offset), quantity=5, unit_price=400, unit_cost=150))
    for offset in range(200, 61, -5):
        sales.append(Sale(product_id=dead.id, store_id=stores[0].id, sold_on=TODAY - timedelta(days=offset), quantity=2, unit_price=250, unit_cost=100))
    session.add_all(sales)

    session.add_all(
        [
            B2BBuyer(
                business_name="BulkMart Wholesale", required_categories=["Accessories"],
                location_city="Bengaluru", lat=12.97, lon=77.6, required_quantity=50,
                maximum_budget=200000, preferred_unit_price=180, reliability_score=0.85,
            )
        ]
    )
    session.add_all(
        [
            User(email="manager@stockmind.demo", full_name="Manager", password_hash=hash_password("demo1234"), role="store_manager", store_id=stores[0].id),
        ]
    )
    session.commit()
    return session
