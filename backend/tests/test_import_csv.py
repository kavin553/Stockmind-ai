from __future__ import annotations

from datetime import date, timedelta

from app.services.data_ingest_service import validate_rows

TODAY = date.today()
KNOWN = {"known_skus": {"SKU-1000", "SKU-1001"}, "known_stores": {"STR-BLR-01"}, "known_categories": {"Apparel"}}


def _rows(*dicts):
    return [dict(d) for d in dicts]


def test_valid_sales_rows_are_accepted():
    accepted, rejected = validate_rows(
        "sales",
        _rows(
            {"sku": "SKU-1000", "store_code": "STR-BLR-01", "sold_on": "2024-05-01", "quantity": "3", "unit_price": "250"},
            {"sku": "SKU-1001", "store_code": "STR-BLR-01", "sold_on": "01/05/2024", "quantity": "1", "unit_price": "99.5"},
        ),
        today=TODAY,
        **KNOWN,
    )
    assert len(accepted) == 2
    assert rejected == []


def test_negative_quantity_is_rejected_but_others_import():
    accepted, rejected = validate_rows(
        "sales",
        _rows(
            {"sku": "SKU-1000", "store_code": "STR-BLR-01", "sold_on": "2024-05-01", "quantity": "-3", "unit_price": "250"},
            {"sku": "SKU-1001", "store_code": "STR-BLR-01", "sold_on": "2024-05-02", "quantity": "2", "unit_price": "99"},
        ),
        today=TODAY,
        **KNOWN,
    )
    assert len(accepted) == 1
    assert len(rejected) == 1
    assert "below" in rejected[0]["reason"] or "negative" in rejected[0]["reason"]


def test_negative_and_zero_price_rejected():
    accepted, rejected = validate_rows(
        "sales",
        _rows(
            {"sku": "SKU-1000", "store_code": "STR-BLR-01", "sold_on": "2024-05-01", "quantity": "1", "unit_price": "-5"},
            {"sku": "SKU-1000", "store_code": "STR-BLR-01", "sold_on": "2024-05-02", "quantity": "1", "unit_price": "0"},
        ),
        today=TODAY,
        **KNOWN,
    )
    assert accepted == []
    assert len(rejected) == 2


def test_malformed_sku_rejected():
    accepted, rejected = validate_rows(
        "products",
        _rows({"sku": "bad sku!", "name": "Thing", "category": "Apparel", "unit_cost": "10", "list_price": "20"}),
        today=TODAY,
        **KNOWN,
    )
    assert accepted == []
    assert "malformed SKU" in rejected[0]["reason"]


def test_unparseable_date_rejected():
    accepted, rejected = validate_rows(
        "sales",
        _rows({"sku": "SKU-1000", "store_code": "STR-BLR-01", "sold_on": "not-a-date", "quantity": "1", "unit_price": "10"}),
        today=TODAY,
        **KNOWN,
    )
    assert accepted == []
    assert "date" in rejected[0]["reason"]


def test_future_date_rejected():
    future = (TODAY + timedelta(days=10)).isoformat()
    accepted, rejected = validate_rows(
        "sales",
        _rows({"sku": "SKU-1000", "store_code": "STR-BLR-01", "sold_on": future, "quantity": "1", "unit_price": "10"}),
        today=TODAY,
        **KNOWN,
    )
    assert accepted == []
    assert "future" in rejected[0]["reason"]


def test_unknown_store_and_sku_rejected():
    accepted, rejected = validate_rows(
        "inventory",
        _rows({"sku": "SKU-9999", "store_code": "STR-BLR-01", "quantity": "5", "first_received_at": "2024-01-01"}),
        today=TODAY,
        **KNOWN,
    )
    assert accepted == []
    assert "unknown SKU" in rejected[0]["reason"]


def test_duplicate_rows_are_collapsed():
    accepted, rejected = validate_rows(
        "sales",
        _rows(
            {"sku": "SKU-1000", "store_code": "STR-BLR-01", "sold_on": "2024-05-01", "quantity": "2", "unit_price": "10"},
            {"sku": "SKU-1000", "store_code": "STR-BLR-01", "sold_on": "2024-05-01", "quantity": "2", "unit_price": "10"},
        ),
        today=TODAY,
        **KNOWN,
    )
    assert len(accepted) == 1
    assert "duplicate" in rejected[0]["reason"]


def test_inventory_cost_above_twice_price_rejected():
    accepted, rejected = validate_rows(
        "products",
        _rows({"sku": "SKU-1000", "name": "Thing", "category": "Apparel", "unit_cost": "100", "list_price": "40"}),
        today=TODAY,
        **KNOWN,
    )
    assert accepted == []
    assert "2x" in rejected[0]["reason"]


def test_unknown_import_kind_raises():
    import pytest

    from app.services.data_ingest_service import RowError

    with pytest.raises(RowError):
        validate_rows("nonsense", [], today=TODAY, **KNOWN)
