from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.main import app


@pytest.fixture()
def client(seeded_db):
    def override():
        yield seeded_db

    app.dependency_overrides[deps.db_session] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    response = client.post("/api/auth/login", json={"email": "manager@stockmind.demo", "password": "demo1234"})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] in ("ok", "degraded")


def test_login_rejects_bad_password(client):
    response = client.post("/api/auth/login", json={"email": "manager@stockmind.demo", "password": "wrong"})
    assert response.status_code == 401


def test_protected_routes_require_a_token(client):
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/inventory").status_code == 401


def test_dashboard_kpis_match_the_service_layer(client, auth_headers, seeded_db):
    response = client.get("/api/dashboard", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    from app.services import dead_stock_service

    expected = dead_stock_service.dashboard_kpis(seeded_db)
    for key, value in expected.items():
        assert payload["kpis"][key] == value, f"{key} is not derived from the database"
    assert "charts" in payload


def test_dead_stock_endpoint_returns_detected_rows(client, auth_headers):
    response = client.get("/api/dead-stock", headers=auth_headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(row["sku"] == "SKU-2291" for row in items)
    row = next(r for r in items if r["sku"] == "SKU-2291")
    assert row["capital_locked"] == 120 * 100.0
    assert row["age_days"] >= 60


def test_inventory_endpoint_paginates_and_filters(client, auth_headers):
    response = client.get("/api/inventory?page=1&page_size=2", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert len(body["items"]) <= 2
    assert body["total"] >= 1
    filtered = client.get("/api/inventory?q=SKU-2291", headers=auth_headers)
    assert all("2291" in row["sku"] for row in filtered.json()["items"])


def test_product_detail_and_forecast(client, auth_headers, seeded_db):
    from sqlalchemy import select

    from app.models import Product

    product = seeded_db.scalars(select(Product).where(Product.sku == "SKU-2291")).one()
    detail = client.get(f"/api/products/{product.id}", headers=auth_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["product"]["sku"] == "SKU-2291"
    assert body["inventory"]
    assert body["inventory"][0]["forecast"]["forecast_30d"] >= 0

    forecast = client.get(f"/api/products/{product.id}/forecast?store=STR-BLR-01", headers=auth_headers)
    assert forecast.status_code == 200
    assert forecast.json()["method"] in ("xgboost", "hist_gradient_boosting", "category_baseline", "seasonal_naive")


def test_recovery_analyze_then_execute_changes_inventory(client, auth_headers, seeded_db):
    from sqlalchemy import select

    from app.models import Inventory, Product, Store

    product = seeded_db.scalars(select(Product).where(Product.sku == "SKU-2291")).one()
    store = seeded_db.scalars(select(Store).where(Store.code == "STR-BLR-01")).one()
    before = seeded_db.scalars(
        select(Inventory).where(Inventory.product_id == product.id, Inventory.store_id == store.id)
    ).one()
    before_qty = before.quantity

    analyzed = client.post(
        "/api/recovery/analyze", json={"product_id": str(product.id), "store_code": "STR-BLR-01"}, headers=auth_headers
    )
    assert analyzed.status_code == 200, analyzed.text
    payload = analyzed.json()
    assert len(payload["agent_results"]) == 4
    plan = payload["plan"]
    assert plan["guardrail_status"] in ("passed", "flagged", "blocked")

    if plan["guardrail_status"] == "blocked" or not plan["allocations"]:
        return

    executed = client.post("/api/recovery/execute", json={"plan_id": plan["id"]}, headers=auth_headers)
    assert executed.status_code == 200, executed.text
    outcome = executed.json()
    assert outcome["after"]["quantity"] <= before_qty
    assert outcome["units_cleared"] >= 0

    seeded_db.expire_all()
    fresh = seeded_db.get(Inventory, before.id)
    assert fresh.quantity == outcome["after"]["quantity"]

    history = client.get("/api/recovery/history", headers=auth_headers)
    assert history.status_code == 200
    assert history.json()["total"] >= 1


def test_execute_is_idempotent_with_same_key(client, auth_headers):
    analyzed = client.post(
        "/api/recovery/analyze", json={"product_id": _sku_to_id(client, auth_headers), "store_code": "STR-BLR-01"}, headers=auth_headers
    )
    plan = analyzed.json()["plan"]
    if plan["guardrail_status"] == "blocked" or not plan["allocations"]:
        return
    first = client.post(
        "/api/recovery/execute", json={"plan_id": plan["id"], "idempotency_key": "fixed-key"}, headers=auth_headers
    )
    assert first.status_code == 200
    replay = client.post(
        "/api/recovery/execute", json={"plan_id": plan["id"], "idempotency_key": "fixed-key"}, headers=auth_headers
    )
    assert replay.status_code == 200
    # The second call must not move stock again.
    assert replay.json()["units_cleared"] == 0


def test_agent_endpoints_return_structured_results(client, auth_headers):
    for path in ("discount", "inter-store-swap", "buy-a-get-b", "b2b"):
        response = client.post(
            f"/api/agents/{path}",
            json={"product_id": _sku_to_id(client, auth_headers), "store_code": "STR-BLR-01"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()["result"]
        assert body["agent"] in ("discount", "inter_store_swap", "buy_a_get_b", "b2b_bulk_buyer")
        assert "expected_net_recovery" in body
        assert 0.0 <= body["confidence"] <= 1.0
        if not body["feasible"]:
            assert body["reason_unavailable"]


def test_stores_and_b2b_endpoints(client, auth_headers):
    stores = client.get("/api/stores", headers=auth_headers)
    assert stores.status_code == 200
    assert len(stores.json()["items"]) == 2
    buyers = client.get("/api/b2b-buyers", headers=auth_headers)
    assert buyers.status_code == 200
    assert buyers.json()["items"][0]["business_name"] == "BulkMart Wholesale"


def test_csv_import_rejects_bad_rows_over_http(client, auth_headers):
    csv = "sku,store_code,sold_on,quantity,unit_price\nSKU-2291,STR-BLR-01,2024-01-05,2,250\nSKU-2291,STR-BLR-01,2024-01-06,-4,250\n"
    response = client.post(
        "/api/import/csv",
        files={"file": ("sales.csv", csv, "text/csv")},
        data={"kind": "sales"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accepted"] == 1
    assert body["rejected"] == 1


def test_demo_run_completes_end_to_end(client, auth_headers):
    response = client.post("/api/recovery/demo-run", json={}, headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["execution"]["after"]["quantity"] <= body["execution"]["before"]["quantity"]
    events = [event["event"] for event in body["timeline"]]
    assert any(event.startswith("agent_") for event in events)
    assert "plan_selected" in events


def _sku_to_id(client, headers) -> str:
    rows = client.get("/api/dead-stock", headers=headers).json()["items"]
    return rows[0]["product_id"] if rows else "00000000-0000-0000-0000-000000000000"
