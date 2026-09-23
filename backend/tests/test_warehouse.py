from __future__ import annotations

from app.services import warehouse_service


def test_parse_location_handles_well_formed_and_bad_codes():
    assert warehouse_service.parse_location("R1-S2") == ("R1", "S2")
    assert warehouse_service.parse_location("r3_s1") == ("R3", "S1")
    assert warehouse_service.parse_location("R2") == ("R2", "S1")
    assert warehouse_service.parse_location("") == ("UNASSIGNED", "UNASSIGNED")
    assert warehouse_service.parse_location("garbage location") == ("UNASSIGNED", "GARBAGE LOCATION")


def test_layout_groups_inventory_into_racks_and_shelves(seeded_db):
    layout = warehouse_service.warehouse_layout(seeded_db, "STR-BLR-01")
    racks = {rack["id"]: rack for rack in layout["racks"]}
    assert set(racks) >= {"R1", "R2", "R3"}

    # R1-S1 holds the dead stock (SKU-2291); R2-S1 holds the fast-moving anchor (SKU-118).
    r1_shelves = {shelf["shelf"]: shelf for shelf in racks["R1"]["shelves"]}
    assert set(r1_shelves) == {"S1"}
    assert r1_shelves["S1"]["total_units"] == 120
    assert racks["R2"]["shelves"][0]["total_units"] == 40

    # Every displayed risk value comes from real rows.
    for rack in layout["racks"]:
        for shelf in rack["shelves"]:
            assert 0.0 <= shelf["risk_score"] <= 1.0
            assert shelf["risk_band"] in ("healthy", "watch", "at_risk", "critical")
            assert shelf["total_value"] >= 0
            assert shelf["unit_count"] == len(shelf["items"])


def test_risk_colour_is_derived_from_data_not_hardcoded(seeded_db):
    layout = warehouse_service.warehouse_layout(seeded_db, "STR-BLR-01")
    shelves = {shelf["location_code"]: shelf for rack in layout["racks"] for shelf in rack["shelves"]}
    dead_shelf = shelves["R1-S1"]  # 120 units, 93 days old, hasn't sold for 61 days
    fast_shelf = shelves["R2-S1"]  # 40 units selling every other day
    assert dead_shelf["risk_score"] > fast_shelf["risk_score"]
    assert dead_shelf["risk_band"] in ("at_risk", "critical")
    assert fast_shelf["risk_band"] in ("healthy", "watch")


def test_location_without_inventory_reports_insufficient_data(seeded_db):
    detail = warehouse_service.location_detail(seeded_db, "STR-BLR-01", "R9-S9")
    assert detail["insufficient_data"] is True
    assert detail["location"] is None


def test_rack_with_no_rows_is_never_assigned_a_risk(seeded_db):
    """A store that stocks nothing must produce zero racks — not fabricated risk."""
    from sqlalchemy import select

    from app.models import Store

    store = Store(code="STR-EMPTY-01", name="Empty", city="Nowhere")
    seeded_db.add(store)
    seeded_db.commit()

    layout = warehouse_service.warehouse_layout(seeded_db, "STR-EMPTY-01")
    assert layout["store"]["code"] == "STR-EMPTY-01"
    assert layout["racks"] == []


def test_unknown_store_raises(seeded_db):
    import pytest

    with pytest.raises(ValueError):
        warehouse_service.warehouse_layout(seeded_db, "STR-NOPE-99")


def test_warehouse_api_endpoint(client_with_auth):
    client, headers = client_with_auth
    response = client.get("/api/warehouse?store=STR-BLR-01", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["store"]["code"] == "STR-BLR-01"
    assert payload["racks"]
    assert all("risk_band" in shelf for rack in payload["racks"] for shelf in rack["shelves"])
