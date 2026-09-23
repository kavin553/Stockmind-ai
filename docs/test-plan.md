# StockMind AI — Test Plan

## 1. Layers under test

| Layer | Tool | Runs without Postgres? |
|---|---|---|
| Pure business math (dead stock, agents, engine, guardrails, verification, elasticity) | pytest | yes |
| CSV validation & normalisation | pytest | yes |
| Feature engineering / forecasting | pytest + sklearn metrics | yes (synthetic series) |
| API routes (TestClient, SQLite in-memory) | pytest + httpx | yes |
| Migrations against Postgres | alembic + CI service container | no |
| Frontend unit/type checks | `tsc --noEmit`, eslint | yes |
| Browser workflow | Playwright | needs the running stack |

The sandbox used to develop this prototype has **no Postgres and no Docker**, so the CI command
`pytest -q` is deliberately scoped to layers that do not require a live database. The DB-backed
integration suite is marked `@pytest.mark.postgres` and skipped automatically when
`DATABASE_URL` is not a Postgres URL.

## 2. Unit test inventory

### Dead-stock engine (`test_dead_stock.py`)
* aging trigger fires at exactly `AGING_DAYS` and not before
* no-sale trigger fires at `NO_SALE_DAYS`
* excess trigger fires when `stock > multiplier × forecast_30d`
* **low stock never triggers recovery**
* risk score is monotonic in age, days-since-sale and excess ratio
* capital locked = `qty × unit_cost`; capital at risk is bounded by capital locked
* KPI aggregation over a mixed fixture matches hand-computed totals

### Discount agent (`test_discount_agent.py`)
* evaluates all six discount candidates when history allows
* never recommends below the margin floor
* higher discount ⇒ higher predicted units cleared (monotonicity)
* returns `feasible=False` for zero stock or missing price
* confidence ∈ [0,1] and is lower for a cold-start SKU than for a rich-history SKU
* payload scenarios are internally consistent (revenue = units × effective price)

### Inter-store swap agent (`test_inter_store_swap_agent.py`)
* rejects a destination whose 30-day demand is already covered by stock
* transfer quantity never exceeds source excess or `TRANSFER_MAX_UNITS`
* rejects when freight exceeds the avoided markdown
* distance increases transfer cost monotonically
* infeasible (not an exception) when there are no peer stores

### Buy-A-Get-B agent (`test_buy_a_get_b_agent.py`)
* refuses anchors below `MIN_ANCHOR_DEMAND`
* refuses incompatible categories (affinity below threshold)
* bundle A/B never equals B/A for the same dead SKU as B, and never pairs B with itself
* free-goods cost is subtracted from recovery
* attach rate rises with anchor demand

### B2B agent (`test_b2b_agent.py`)
* rejects buyers whose category does not match
* never offers below `unit_cost × b2b_floor_pct`
* respects buyer `maximum_budget` and `required_quantity`
* proximity weight reduces score for distant buyers
* returns the best of several eligible buyers by net recovery

### Recovery engine (`test_recovery_engine.py`)
* all four agents are invoked for a normal case
* one infeasible agent does not abort the run
* `expected_net_recovery` subtracts action cost, promotional cost, friction and risk
* negative net recovery options are never selected
* **no strategy may allocate units another strategy already allocated**
* total allocated units ≤ available units, and no allocation is negative
* hybrid is chosen only when it beats the single best by `HYBRID_MIN_IMPROVEMENT`
* hybrid allocations are non-negative and sum correctly

### Guardrails (`test_guardrails.py`)
* discount above `MAX_AUTONOMOUS_DISCOUNT` ⇒ `flagged`
* net recovery below the floor ⇒ `blocked`
* B2B price under the floor ⇒ `blocked`
* transfer above `TRANSFER_MAX_UNITS` ⇒ `blocked`
* quantity ≤ 0 ⇒ `blocked`
* a clean plan ⇒ `passed`

### Verification (`test_verification.py`)
* variance = `(simulated - predicted) / predicted`
* zero predicted value does not divide by zero
* every verification row is labelled `prototype_simulation`

### Forecasting (`test_forecast.py`)
* feature windows are computed on a time-ordered series and never use future rows
* time-based split: validation rows all come after training rows
* cold start (few sales) yields `method = category_baseline` and low confidence
* forecasts are non-negative and `forecast_60d >= forecast_30d >= forecast_7d` for stable series
* reported metrics come from the holdout, not the training set

### Warehouse / 3D digital twin (`test_warehouse.py`)
* location codes parse into rack + shelf, including missing and malformed codes
* inventory groups into racks and shelves with correct totals
* **rack risk is derived from data** — the aged shelf scores higher than the fast mover
* a location with no inventory reports `insufficient_data`
* a store stocking nothing produces **zero racks** (no fabricated risk)
* unknown store raises
* `GET /api/warehouse` returns shelves carrying a `risk_band`

### CSV import (`test_import_csv.py`)
* negative quantity → row rejected, others imported
* malformed SKU → rejected
* unparseable date → rejected
* duplicate rows collapsed (no duplicate transactions)
* valid file → all rows accepted

## 3. Browser tests (Playwright)

`tests/e2e/`:
1. login with the demo manager account
2. dashboard KPIs render and match `GET /api/dashboard`
3. dead-stock table loads rows and filters by store
4. product detail shows age explanation and forecast chart
5. recovery studio: analyze → four agent cards visible → execute → before/after changes
6. action history shows the executed action
7. B2B market shows buyers
8. autonomous demo run completes and the timeline contains all four agent steps

## 4. Commands

```bash
# backend
cd backend && pytest -q               # 111 tests, full non-Postgres suite
cd backend && pytest -q -m postgres   # integration (needs DATABASE_URL)

# frontend
cd frontend && npm run lint && npm run typecheck

# browser
cd tests && npx playwright install && npx playwright test
```

## 5. Exit criteria

* `pytest -q` green, no skips other than the documented Postgres marker.
* `tsc --noEmit` and eslint clean.
* No route returns 500 during the judge workflow.
* No dashboard value is hardcoded — each is traced to a query in the API tests.
