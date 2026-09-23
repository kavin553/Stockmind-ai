# StockMind AI — Agent Design

There are **exactly four AI agents**. The Dead Stock Detection Engine, Demand Forecast Service,
Recovery Decision Engine, Guardrail Service, Execution Service, Verification Service and Audit
Service are normal software services — never described as agents.

Every agent:

1. receives structured data (a `RecoveryContext`, never the ORM),
2. evaluates a recovery opportunity with a real calculation,
3. returns `expected_units_cleared`, `expected_recovery`, `expected_loss`, `action_cost`,
4. returns a `confidence` derived from data sufficiency (never a made-up constant),
5. returns human-readable `reasons` computed from the numbers,
6. returns structured JSON,
7. handles missing inputs by returning `feasible=False` with an explanation — it must never raise.

## Shared input — `RecoveryContext`

```python
class RecoveryContext(BaseModel):
    product: ProductSpec          # sku, name, category, unit_cost, list_price, b2b_floor_pct
    store: StoreSpec              # id, code, city, lat, lon
    inventory: InventorySpec      # quantity, discount_pct, first_received_at, last_sold_at
    metrics: InventoryMetrics     # age_days, days_since_sale, velocity, excess_units, risk_score
    forecast: ForecastBundle      # forecast_7d/30d/60d, confidence, method
    recent_sales: list[SalePoint]
    previous_discounts: list[float]
    peer_stores: list[StoreDemand]        # destination candidates with their own forecast/stock
    bundle_candidates: list[BundleCandidate]   # high-demand anchors in compatible categories
    b2b_buyers: list[BuyerSpec]
    policy: PolicySpec            # thresholds + margins
```

## Shared output — `AgentResult`

```json
{
  "agent": "discount",
  "feasible": true,
  "reason_unavailable": null,
  "expected_units_cleared": 0,
  "expected_recovery": 0,
  "expected_loss": 0,
  "action_cost": 0,
  "confidence": 0.0,
  "reasons": [],
  "payload": {}
}
```

---

## Agent 1 — Discount Agent (`discount_agent.py`)

**Job.** Decide whether controlled discounting clears the dead stock with acceptable recovery.

**Method.**
* Candidate discounts: `5,10,15,20,25,30 %`.
* For each discount `d`:
  * elasticity lift from the product's category (`elasticity`) and its own observed
    discount→sales response if history exists:
    `lift = 1 + elasticity * (d / (1 - d))`, damped by a freshness factor.
  * `predicted_units = min(stock, baseline_30d * lift * horizon_fraction)`
  * `effective_price = list_price * (1 - d)`
  * `revenue = predicted_units * effective_price`
  * `margin = predicted_units * (effective_price - unit_cost)`
  * `recovery = revenue` (value recovered), `loss = predicted_units * (list_price - effective_price)`
    for the discounted units, plus cost of remaining unsold units discounted at the aged-stock
    salvage rate.
* Rejects any scenario whose **margin floor** (`unit_cost * (1 + MIN_MARGIN_PCT)`) is violated.
* Picks the feasible scenario maximising **net recovery**, not raw revenue.

**Confidence.** `0.4 * history_adequacy + 0.3 * forecast_confidence + 0.3 * sales_regularity`,
where `history_adequacy = min(1, observed_days / 180)`.

**Reasons.** e.g. *"A 20% discount clears an estimated 74 of 120 units, recovering 62.1% of
locked capital; scenarios above 25% breach the margin floor."*

---

## Agent 2 — Inter-Store Swap Agent (`inter_store_swap_agent.py`)

**Job.** Move stock from a weak-demand store to a stronger-demand store.

**Method.** For every peer store `s`:
* `demand_30d(s) = forecast_30d(s)`
* `available_at_s = inventory_qty(s)`
* `headroom = max(0, demand_30d(s) - available_at_s)`
* `transfer_qty = min(source_excess, headroom, TRANSFER_MAX_UNITS)`
* `transfer_cost = base_handling * transfer_qty + rate_per_km * distance_km`
* `expected_recovery = transfer_qty * effective_price(s)` where `effective_price(s)` is the
  destination's expected realised price **without** the markdown that the source would need.
* `avoided_markdown = transfer_qty * (list_price - expected_markdown_price(source))`
* Feasible only when `transfer_qty >= TRANSFER_MIN_UNITS` **and**
  `expected_recovery - transfer_cost > 0` **and** the destination demand exceeds its supply
  by a meaningful margin (`headroom >= TRANSFER_MIN_UNITS`).

**Confidence.** Scales with destination demand sufficiency and inverse transfer distance.

**Reasons.** *"Store STR-BLR-02 shows 30-day demand of 88 units against 21 on hand; moving 40
units costs ₹1,240 in freight and avoids a 20% markdown worth ₹6,800."*

---

## Agent 3 — Buy-A-Get-B Combo Agent (`buy_a_get_b_agent.py`)

**Job.** Use a high-demand product A to clear dead-stock product B.

**Candidate offer types**
| type | mechanic |
|---|---|
| `buy_a_get_b_free` | A at full price, B free |
| `buy_a_get_b_reduced` | A at full price, B at 40% off |
| `buy_2a_get_b` | two A, one B free |
| `bundle_ab` | fixed-price A+B set |

**Compatibility is computed, never random:**
```
compatibility = w1 * category_affinity(A.category, B.category)      # from categories.co_purchase_affinity
              + w2 * co_purchase_rate(A, B)                         # historical same-basket proxy
              + w3 * price_band_similarity(A, B)
              + w4 * margin_room(A)                                 # can A absorb the giveaway?
```
Only anchors with `compatibility >= MIN_BUNDLE_COMPATIBILITY` and healthy demand
(`forecast_30d(A) >= MIN_ANCHOR_DEMAND`) are considered.

**Economics.**
* `attach_rate = compatibility * base_attach * demand_factor(A)`
* `predicted_b_cleared = min(stock_b, forecast_30d(A) * attach_rate)`
* `incentive_cost = predicted_b_cleared * (effective_price_b - realised_price_b)` + free-goods cost
* `recovery = predicted_b_cleared * realised_price_b` (0 for free) + incremental A margin
* `loss = predicted_b_cleared * unit_cost_b - A_margin_gain` floored at 0 for reporting.

**Reasons.** *"Bundle with SKU-A-118 (30-day demand 210, category affinity 0.78): estimated
attach rate 12% clears 41 units; the anchor's margin absorbs the giveaway cost."*

---

## Agent 4 — B2B Bulk Buyer Agent (`b2b_bulk_buyer_agent.py`)

**Job.** Place hard-to-clear inventory with a bulk buyer.

**Matching score** (0..1), weighted:
```
0.30 * category_match          # buyer.required_categories ∩ product.category
0.20 * quantity_fit            # min(stock, needed) / max(stock, needed)
0.15 * price_compatibility     # proximity of buyer.preferred_unit_price to our ask
0.15 * demand_urgency          # how dead the stock is
0.10 * proximity               # 1 - normalised_distance
0.10 * buyer_reliability
```
Eligible buyers must match the category, satisfy `required_quantity <= stock`,
`preferred_unit_price >= floor = unit_cost * b2b_floor_pct`, and budget ≥ deal value.

**Offer.** The agent asks `max(floor, min(preferred_price, list_price * 0.75))`, then settles
quantity at the buyer's minimum lot while leaving a retail-capable remainder if the engine will
build a hybrid plan.

**Reasons.** *"Buyer 'BulkMart Wholesale' needs 100+ units of Apparel; 63 units clear at ₹420/unit
(3.4% above the cost floor), recovering 47.6% of locked capital with 0.82 reliability."*

---

## Recovery Decision Engine (`recovery_engine.py`)

Normalises the four `AgentResult`s, computes `expected_net_recovery` for each with
`app/config.py` coefficients, then:

1. **Single strategy** — argmax net recovery among feasible options.
2. **Hybrid** — enumerate bounded allocations of the SKU's units across strategies
   (coarse weight steps), keep the split with the highest net recovery subject to
   no-double-counting and non-negativity.
3. Keep the hybrid only when it **strictly** beats the best single strategy by
   `HYBRID_MIN_IMPROVEMENT` (default 3%).

The plan carries an explanation assembled purely from the winning numbers.

## Guardrail Service (`guardrail_service.py`)

Deterministic, no ML. Checks: minimum margin, maximum autonomous discount, transfer limits,
B2B price floor, quantity limits, negative net recovery, invalid product combinations.
Outcomes: `passed` / `flagged` (manual review) / `blocked`.
