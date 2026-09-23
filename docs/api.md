# StockMind AI — API Design

Base URL: `http://localhost:8000`. All endpoints are under `/api`. JSON only.
Auth: `POST /api/auth/login` issues a signed token; protected routes expect
`Authorization: Bearer <token>`.

## Conventions

* Money: JSON number, 2 decimals, INR by default (currency is a setting, not hardcoded).
* Errors: `{"detail": "..."}` with proper HTTP status (400 validation, 401 auth, 404 missing,
  409 conflict/idempotency, 422 schema).
* List endpoints accept `page`, `page_size` (default 50, max 200) and return
  `{"items": [...], "total": n, "page": p, "page_size": s}`.

## Auth

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| POST | `/api/auth/login` | `{email, password}` | `{token, user}` |
| GET | `/api/auth/me` | — | current user |

## Dashboard

| Method | Path | Returns |
|---|---|---|
| GET | `/api/dashboard` | KPIs + chart series, all computed from DB |
| GET | `/api/dashboard/kpis` | KPI block only |

KPI payload:
```json
{
  "current_inventory_value": 0,
  "dead_stock_value": 0,
  "dead_stock_units": 0,
  "dead_stock_pct": 0,
  "capital_locked": 0,
  "capital_at_risk": 0,
  "expected_recovery": 0,
  "expected_loss": 0,
  "avg_inventory_age_days": 0,
  "critical_skus": 0,
  "recovery_rate": 0,
  "storage_volume_m3": 0,
  "dead_stock_storage_m3": 0
}
```
Charts: `dead_stock_by_category`, `aging_buckets`, `strategy_distribution`,
`capital_at_risk_series`, `forecast_vs_actual`.

## Inventory & products

| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/api/inventory` | `store`, `category`, `q`, `sort`, `page` | inventory rows |
| GET | `/api/dead-stock` | `store`, `category`, `risk`, `strategy`, `min_age`, `page` | dead-stock rows |
| GET | `/api/products/{id}` | — | product + inventory + metrics + forecast |
| GET | `/api/products/{id}/forecast` | `store`, `refresh` | forecast bundle |
| GET | `/api/products/{id}/recovery-options` | `store` | four agent results (not yet a plan) |

Dead-stock row:
```json
{
  "case_id": "…", "product_id": "…", "sku": "SKU-2291", "name": "…",
  "store": "STR-BLR-01", "quantity": 120, "age_days": 93, "days_since_sale": 61,
  "forecast_30d": 31.5, "risk_band": "critical", "risk_score": 0.87,
  "capital_locked": 42000, "best_strategy": "buy_a_get_b", "expected_recovery": 26100
}
```

## Recovery

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/recovery/analyze` | `{product_id, store_id}` | `{case, agent_results, plan}` |
| POST | `/api/recovery/execute` | `{plan_id, idempotency_key?}` | `{actions, action_results, before, after}` |
| GET | `/api/recovery/history` | `page`, `status` | executed actions + outcomes |
| GET | `/api/recovery/{plan_id}` | — | plan detail |
| GET | `/api/recovery/{plan_id}/timeline` | — | ordered execution events from audit rows |
| POST | `/api/recovery/demo-run` | `{scenario?}` | runs the deterministic autonomous demo |

## Stores & B2B

| Method | Path | Returns |
|---|---|---|
| GET | `/api/stores` | stores with stock value, dead-stock value, demand |
| GET | `/api/stores/by-id/{id}` | store detail |
| GET | `/api/stores/transfer-opportunities` | computed source→destination candidates |
| GET | `/api/b2b-buyers` | buyers + match opportunities |

## Warehouse (3D digital twin)

Rack and shelf risk is derived from real inventory rows. A location with no inventory is returned
with `unit_count = 0` so the client renders **"Insufficient inventory data"** instead of a
fabricated risk colour.

| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/api/warehouse` | `store` (code, optional) | `{store, racks[], generated_at}` |
| GET | `/api/warehouse/location/{location_code}` | `store` (required) | one shelf with its inventory rows |

Rack payload:
```json
{
  "id": "R1",
  "shelf_count": 2,
  "total_units": 160,
  "total_value": 20000,
  "risk_score": 0.61,
  "risk_band": "at_risk",
  "shelves": [
    {
      "location_code": "R1-S1",
      "shelf": "S1",
      "unit_count": 1,
      "total_units": 120,
      "total_value": 12000,
      "risk_score": 0.87,
      "risk_band": "critical",
      "recovery_candidates": 1,
      "items": [
        {"product_id": "…", "store_id": "…", "sku": "SKU-2291", "quantity": 120,
         "capital_locked": 12000, "risk_band": "critical", "age_days": 93, "days_since_sale": 61}
      ]
    }
  ]
}
```

## Agents (direct invocation)

Each accepts the same `RecoveryContext` shape (or `{product_id, store_id}` to have the server
assemble it) and returns an `AgentResult`. Useful for tests and for the UI's "evaluate" calls.

| Method | Path |
|---|---|
| POST | `/api/agents/discount` |
| POST | `/api/agents/inter-store-swap` |
| POST | `/api/agents/buy-a-get-b` |
| POST | `/api/agents/b2b` |

## Import

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/import/csv` | multipart `file`, `kind` (`sales`\|`inventory`\|`products`) | `{accepted, rejected, errors[]}` |

Validation rejects: negative quantity, negative or zero price, cost > 2× list price,
malformed SKU, unparseable dates, unknown store/category, duplicate rows. Rejections are
reported per row; valid rows are still imported.

## Health

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | `{status, database, version}` |
| GET | `/api/health/live` | liveness (no DB) |
