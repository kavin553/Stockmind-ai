# StockMind AI — Architecture

## 1. Purpose

StockMind AI answers one question: **"How do we clear dead stock with the least possible loss?"**

It is *not* an inventory CRUD product. Inventory screens exist only to support the dead-stock
recovery loop:

```
DEAD STOCK  ->  RECOVERY STRATEGY  ->  CLEARANCE  ->  RECOVERED VALUE
```

## 2. System context

```
+---------------------+         +-------------------------------------------+
|  Next.js frontend   |  REST   |              FastAPI backend              |
|  (App Router, TS)   | <-----> |                                           |
|                     |         |  api/routes  -> services -> agents        |
|  Dashboard          |         |       |            |          |          |
|  Dead Stock Center  |         |       v            v          v          |
|  Product Detail     |         |   database     4 agents   guardrails     |
|  Recovery Studio    |         |   (SQLAlchemy)  (pure)    execution      |
|  Store Network      |         |       |                                  |
|  B2B Market         |         |       v                                  |
|  Action History     |         |  PostgreSQL                              |
+---------------------+         +-------------------------------------------+
```

The browser never touches the database. All reads/writes go through the REST API.

## 3. Layers

### 3.1 API layer (`app/api`)
Thin HTTP transport. Validates with Pydantic schemas, delegates to services, returns DTOs.
No business math lives here.

### 3.2 Service layer (`app/services`)
| Service | Responsibility |
|---|---|
| `dead_stock_service` | Classification of recovery candidates, KPI aggregation, capital-at-risk |
| `demand_forecast_service` | Feature assembly + model inference; cold-start fallback |
| `recovery_engine` | Orchestrates the four agents, normalises results, scores, builds single/hybrid plans |
| `guardrail_service` | Deterministic policy checks after agents, before execution |
| `execution_service` | Simulated execution — mutates inventory/promotions/transfers/orders |
| `verification_service` | Predicted vs simulated outcome comparison |
| `audit_service` | Append-only audit trail |
| `data_ingest_service` | CSV validation + upsert |

### 3.2b Warehouse service (`app/services/warehouse_service.py`)
Groups inventory rows by physical `location_code` (`R1-S2`) so the 3D digital twin can colour
racks from real risk data. Locations with no rows are reported as `insufficient_data`.

### 3.3 Agent layer (`app/agents`)
Exactly four AI agents. Each is a **pure function over structured input**:

```python
class AgentResult(BaseModel):
    agent: Literal["discount","inter_store_swap","buy_a_get_b","b2b_bulk_buyer"]
    feasible: bool
    reason_unavailable: str | None
    expected_units_cleared: float
    expected_recovery: float
    expected_loss: float
    action_cost: float
    confidence: float          # 0..1, derived from data sufficiency
    reasons: list[str]
    payload: dict              # agent-specific detail (e.g. per-discount scenarios)
```

Agents never read the database directly; the engine supplies them a `RecoveryContext`.
This keeps them unit-testable and crash-isolated (an infeasible agent returns
`feasible=False`, it never raises).

### 3.4 ML layer (`app/ml`)
* `features.py` — rolling windows (`sales_7d`…`sales_60d`), trend, volatility, calendar flags.
* `forecast.py` — XGBoost regressor with **time-ordered** validation; deterministic fallback
  (seasonal-naive + trend damping) when history is too short or the model is unavailable.

### 3.5 Persistence (`app/database`, `app/models`)
SQLAlchemy 2.0 declarative models, Postgres via `psycopg`. Alembic owns schema versioning.

## 4. Data flow — a recovery run

```
1. dead_stock_service.find_candidates()
        -> RecoveryCandidate(product, store, inventory, metrics)
2. demand_forecast_service.forecast_for(product, store)
        -> forecast_7d/30d/60d + confidence + method
3. recovery_engine.analyze(candidate)
        -> build RecoveryContext
        -> run 4 agents (in-process, one failing agent cannot abort the run)
        -> normalise + compute expected_net_recovery for each
        -> solve single-best vs hybrid allocation
4. guardrail_service.evaluate(plan)  -> pass | flag | block
5. execution_service.execute(plan)   -> DB mutations + audit rows
6. verification_service.verify(plan) -> predicted vs simulated
7. dashboard recomputes from DB
```

## 5. Expected net recovery (the comparison metric)

Raw revenue is *not* the ranking metric. For every option:

```
expected_net_recovery =
      expected_recovery
    - action_cost              # e.g. transfer freight, promo setup
    - promotional_cost         # value of the free/discounted B in a bundle
    - margin_penalty           # erosion vs. holding at list price
    - execution_friction       # small modelled cost by strategy complexity
    - risk_penalty             # (1 - confidence) * expected_recovery * RISK_WEIGHT
```

All coefficients live in `app/config.py` and are configurable.

## 6. Hybrid plans

The engine may split one SKU's dead stock across strategies. It enumerates a bounded set of
allocations (default: 3 strategies × coarse weight grid) and keeps the best feasible split
whose **net recovery strictly exceeds** the best single strategy. Two hard invariants:

* `sum(allocated units) <= available units` (no double counting)
* every allocation `>= 0`

## 7. Guardrails

Run after agents, before execution. Deterministic, no ML. Violations are `flag` (manual
review) or `block` (cannot execute). Examples: discount above the autonomous ceiling,
B2B price under the floor, negative net recovery, invalid product pairing, transfer over
the per-move limit, quantity below the transfer minimum.

## 8. Execution model

Simulated but **stateful**: every action writes real rows.

| Strategy | DB effect |
|---|---|
| Discount | inventory `discount_pct`, `effective_price`; promotion row |
| Inter-store swap | source qty −, destination qty +; `store_transfers` row |
| Buy-A-Get-B | `promotions` row + expected B units decremented on execution |
| B2B | `b2b_orders` row + inventory decrement |

All mutations occur in one transaction with the audit row.

## 9. Verification loop

After execution a verification record stores predicted vs simulated clearance and recovery.
The simulation applies the seeded demand elasticity to the same product history, so the numbers
are internally consistent — they are **prototype simulation, never real-world measurement**,
and the UI labels them as such.

## 10. Non-goals

* No enterprise IdP (local demo auth with role claims).
* No real POS / payment / marketplace integrations (clean connector interfaces + mocks).

## 11. 3D digital twin

`/warehouse` renders racks and shelves with React Three Fiber. Each shelf's colour comes from
`risk_band` computed over the inventory rows stored at that location; clicking a shelf calls
`GET /api/warehouse/location/{code}` and shows the actual SKUs. A location with no inventory
displays **"Insufficient inventory data"** — no risk is ever fabricated to fill the scene. The
scene is capped at 12 racks × 7 shelves and uses low-power WebGL settings to stay stable.
