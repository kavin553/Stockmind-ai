# StockMind AI — Database Design

PostgreSQL, accessed through SQLAlchemy 2.0 (`postgresql+psycopg://`). Schema is versioned by
Alembic. All money columns are `Numeric(12,2)`; quantities are integers.

## 1. Entity map

```
users ─┐
       │ (audit actor)
stores ──< inventory >── products ──< sales
   │                        │
   │                        └── categories
   ├──< store_transfers
   ├──< promotions
   b2b_buyers ──< b2b_orders
recovery_cases ──< agent_results
       │
       └──< recovery_plans ──< actions ──< action_results
                                     └──< audit_logs
settings (key/value)
forecasts >── products, stores
```

## 2. Tables

### users
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| email | citext unique | login |
| full_name | text | |
| password_hash | text | bcrypt |
| role | text | `store_manager` \| `inventory_staff` |
| store_id | uuid fk stores nullable | staff are scoped to a store |
| is_active | bool | |
| created_at | timestamptz | |

### stores
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| code | text unique | e.g. `STR-BLR-01` |
| name | text | |
| city, region | text | |
| lat, lon | numeric | used by the transfer-distance cost |
| is_active | bool | |

### categories
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| name | text unique | |
| parent_id | uuid fk categories | nullable |
| elasticity | numeric | price elasticity used by the discount agent |
| co_purchase_affinity | jsonb | category → affinity score (0..1) for bundles |

### products
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| sku | text unique | validated `^[A-Z0-9][A-Z0-9\-]{2,31}$` |
| name | text | |
| category_id | uuid fk | |
| unit_cost | numeric | |
| list_price | numeric | |
| b2b_floor_pct | numeric | fraction of unit_cost that is the B2B price floor |
| dimensions_cm | jsonb | {l,w,h} for storage volume |
| is_active | bool | |

Indexes: `products(sku)` unique, `products(category_id)`.

### inventory
One row per (product, store) — the current snapshot.
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| product_id | uuid fk | |
| store_id | uuid fk | |
| quantity | int | `CHECK (quantity >= 0)` |
| discount_pct | numeric | 0..60 |
| first_received_at | date | drives inventory age |
| last_sold_at | date | drives days-since-sale |
| location_code | text | rack/shelf label |
| updated_at | timestamptz | |

Unique: `(product_id, store_id)`. Index: `(store_id)`, `(last_sold_at)`.

### sales
| column | type | notes |
|---|---|---|
| id | bigserial pk | |
| product_id | uuid fk | |
| store_id | uuid fk | |
| sold_on | date | |
| quantity | int | `CHECK (quantity > 0)` |
| unit_price | numeric | actual transacted price |
| unit_cost | numeric | cost snapshot |
| is_promotion | bool | |

Index: `(product_id, store_id, sold_on)`. 12 months of history per product/store.

### b2b_buyers
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| business_name | text | |
| required_categories | jsonb | list of category names |
| location_city | text | |
| lat, lon | numeric | |
| required_quantity | int | minimum lot size |
| maximum_budget | numeric | |
| preferred_unit_price | numeric | |
| reliability_score | numeric | 0..1 |

### forecasts
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| product_id, store_id | fk | |
| as_of | date | forecast origin |
| horizon_days | int | 7/30/60 |
| predicted_units | numeric | |
| confidence | numeric | 0..1 |
| method | text | `xgboost` \| `seasonal_naive` \| `category_baseline` |
| model_metrics | jsonb | MAE / RMSE / sMAPE from time-based holdout |
| created_at | timestamptz | |

Unique: `(product_id, store_id, as_of, horizon_days)`.

### recovery_cases
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| product_id, store_id | fk | |
| detected_at | timestamptz | |
| triggers | jsonb | e.g. `["aging","no_sale","excess"]` |
| age_days | int | snapshot at detection |
| days_since_sale | int | |
| forecast_30d | numeric | |
| excess_units | numeric | stock − multiplier × forecast |
| stock_units | int | |
| capital_locked | numeric | qty × unit_cost |
| capital_at_risk | numeric | qty × unit_cost × risk factor |
| risk_score | numeric | 0..1 |
| risk_band | text | `healthy` \| `watch` \| `at_risk` \| `critical` |
| status | text | `open` \| `planned` \| `executed` \| `verified` \| `closed` |

Index: `(status)`, `(store_id)`, `(risk_band)`.

### agent_results
One row per agent per case.
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| case_id | uuid fk recovery_cases | |
| agent | text | the four agent keys |
| feasible | bool | |
| reason_unavailable | text | |
| expected_units_cleared | numeric | |
| expected_recovery | numeric | |
| expected_loss | numeric | |
| action_cost | numeric | |
| expected_net_recovery | numeric | computed by the engine |
| confidence | numeric | |
| reasons | jsonb | list[str] |
| payload | jsonb | full scenario detail |
| created_at | timestamptz | |

Index: `(case_id, agent)`.

### recovery_plans
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| case_id | uuid fk | |
| strategy | text | `single` \| `hybrid` |
| allocations | jsonb | `[{agent, units, expected_net_recovery}]` |
| expected_recovery | numeric | |
| expected_loss | numeric | |
| total_action_cost | numeric | |
| expected_net_recovery | numeric | ranking metric |
| confidence | numeric | |
| guardrail_status | text | `passed` \| `flagged` \| `blocked` |
| guardrail_findings | jsonb | |
| explanation | text | generated from real values |
| created_at | timestamptz | |

### actions
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| plan_id | uuid fk | |
| case_id | uuid fk | |
| agent | text | |
| units | int | |
| status | text | `pending` \| `executed` \| `failed` \| `skipped` |
| idempotency_key | text unique | blocks duplicate transactions |
| executed_at | timestamptz | |
| result_summary | jsonb | |

### action_results
Post-execution verification for an action.
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| action_id | uuid fk | |
| predicted_units | numeric | |
| simulated_units | numeric | |
| predicted_recovery | numeric | |
| simulated_recovery | numeric | |
| variance_pct | numeric | |
| label | text | always `prototype_simulation` |

### promotions
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| kind | text | `discount` \| `buy_a_get_b` |
| product_id | uuid fk | product B (the dead stock) |
| anchor_product_id | uuid fk nullable | product A |
| store_id | uuid fk nullable | |
| discount_pct | numeric | |
| incentive | text | `free` \| `reduced` |
| starts_on, ends_on | date | |
| created_by_action_id | uuid fk actions | |

### store_transfers
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| product_id | uuid fk | |
| source_store_id, destination_store_id | fk | `CHECK (source <> destination)` |
| quantity | int | `CHECK (quantity > 0)` |
| transfer_cost | numeric | |
| status | text | `planned` \| `in_transit` \| `completed` |
| created_by_action_id | uuid fk actions | |

### b2b_orders
| column | type | notes |
|---|---|---|
| id | uuid pk | |
| buyer_id | uuid fk | |
| product_id | uuid fk | |
| store_id | uuid fk | |
| quantity | int | |
| unit_price | numeric | |
| total_value | numeric | |
| status | text | `draft` \| `confirmed` \| `fulfilled` |
| created_by_action_id | uuid fk actions | |

### audit_logs
Append-only.
| column | type | notes |
|---|---|---|
| id | bigserial pk | |
| occurred_at | timestamptz | |
| actor | text | user email or `system` |
| actor_type | text | `user` \| `system` |
| sku | text | |
| trigger | text | |
| agent | text nullable | |
| decision | text | |
| inputs_summary | jsonb | |
| recommendation | jsonb | |
| confidence | numeric | |
| execution_result | jsonb | |

Index: `(occurred_at desc)`, `(sku)`.

### settings
| column | type | notes |
|---|---|---|
| key | text pk | |
| value | jsonb | |
| updated_at | timestamptz | |

Seeded with the default thresholds (`AGING_DAYS`, `NO_SALE_DAYS`, `EXCESS_STOCK_MULTIPLIER`,
`MAX_AUTONOMOUS_DISCOUNT`, `MIN_MARGIN_PCT`, `B2B_PRICE_FLOOR_PCT`, `TRANSFER_MAX_UNITS`).

## 3. Invariants

* `inventory.quantity >= 0` enforced by CHECK + service-level validation.
* `store_transfers.source_store_id <> destination_store_id`.
* Execution is transactional: hypothesis rows for a case are locked with `SELECT … FOR UPDATE`
  before units are moved.
* `actions.idempotency_key` is unique, so a double-click cannot clear the same stock twice.
* Audit rows are never updated or deleted.
