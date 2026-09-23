# Judge Demo Script (5 minutes)

## Before the judges arrive

```bash
cp .env.example .env
docker compose up --build          # first run seeds 252 products + 12 months of sales
```

Wait for the backend log to show the seed summary, then open <http://localhost:3000>.

*Docker-free alternative:* `make migrate && make seed && make backend` then `make frontend` in a
second terminal (needs a local PostgreSQL).

**Accounts** — password `demo1234`

| Email | Role |
|---|---|
| `manager@stockmind.demo` | Store Manager |
| `inventory@stockmind.demo` | Inventory Staff |

## The walkthrough

### 1. Login (10 s)
Sign in. Note the "API connected" indicator — the UI has no local data at all.

### 2. Dashboard (45 s)
Point out that every number is aggregated from the database:
Dead Stock Value, Capital Locked, Capital at Risk, Critical SKUs, Average Inventory Age,
Recovery Rate, storage volume occupied by dead stock.
Charts: dead-stock value by category, inventory ageing, recovery-strategy distribution,
capital at risk, forecast vs actual.

**Say:** *"Nothing on this screen is hardcoded. Delete the inventory table and it all reads zero."*

### 3. Dead Stock Center (45 s)
The main operational screen. Filter by store and risk band, sort by capital locked.
Highlight the columns: Age, Days Since Sale, 30-Day Forecast, Dead Stock Risk, Capital Locked,
Best Recovery Strategy, Expected Net Recovery.

**Say:** *"Low stock is never listed here. A thin, fast-selling SKU is a replenishment problem —
the engine deliberately refuses to treat it as dead stock."*

### 4. Product Detail (30 s)
Open any SKU. Show the sales trend flattening, the forecast with its holdout metrics and
confidence, and the trigger badges explaining *why* it is a recovery candidate.

### 5. Recovery Studio — the hero (90 s)
Click **Analyze Recovery** on a dead-stock SKU.

* Four agent cards side by side, each with units cleared, expected recovery, expected loss,
  action cost, net recovery, confidence, and plain-language reasons.
* Some cards will read **Not feasible** with an explanation — that is by design, not a bug.
* The comparison chart shows gross vs **net** recovery.
* The recommended plan shows the selected strategy (or a **hybrid** split), the guardrail verdict,
  and an explanation built from the actual numbers.

**Say:** *"Raw revenue is not the ranking metric. We subtract action cost, execution friction and a
confidence-weighted risk penalty. A hybrid plan is only used when it strictly beats the best single
strategy, and no strategy can ever allocate stock another one already claimed."*

Click **Execute Plan**. Show Before / After: units on hand fall, capital locked falls, and the
verification block reads *Predicted / Simulated / Variance*.

**Say:** *"That is simulated execution — it wrote real rows to the database and the audit trail.
The outcome comparison is labelled Prototype Simulation because it is a seeded demand model, not a
real-world measurement."*

### 6. Run Autonomous Recovery (45 s)
Go back to the Dashboard and press **Run Autonomous Recovery** (or open `/recovery-studio?demo=1`).

Watch the timeline populate from stored events:
case detected → each of the four agents → plan selected → guardrails → action executed → audit.
It ends with a before/after diff on the database.

### 7. Store Network & B2B Market (30 s)
**Store Network** — store cards with dead-stock exposure and the transfer opportunities the
Inter-Store Swap Agent found, each with freight versus avoided markdown.

**B2B Market** — the bulk buyers and how each is scored (category fit, quantity, price,
urgency, distance, reliability).

### 8. Action History (20 s)
Every executed action with its guardrail status and predicted vs simulated outcome.

## Closing line

> **Don't just discount dead stock. Find its best recovery path.**
> Detect → Evaluate → Recover → Verify.

## If something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Dashboard empty | Seed has not run | `make seed` (or re-run `docker compose up`) |
| "No dead-stock candidates" | Seed ran with `--skip-forecast` | Re-run `python -m app.seed.seed` (forecasts are needed for the demand comparison) |
| Login fails | Backend not up | `curl localhost:8000/api/health` |
| Execute button disabled | Guardrails returned `blocked` | Read the finding text — pick another SKU, or use the autonomous run which skips blocked candidates |
