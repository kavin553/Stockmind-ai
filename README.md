# StockMind AI

**Multi-Agent Dead Stock Recovery Platform for Retail**

> Don't just discount dead stock. Find its best recovery path.

StockMind AI detects aging / dead inventory, forecasts demand, and runs **four specialized
agents** — Discount, Inter-Store Swap, Buy-A-Get-B, and B2B Bulk Buyer — to determine the
recovery route that maximises **expected net recovery** (recovery minus costs, friction and risk).

```
DETECT  ->  EVALUATE  ->  RECOVER  ->  VERIFY
```

---

## 1. Repository layout

```
stockmind-ai/
  backend/            FastAPI + SQLAlchemy + Alembic, agents, services, ML
  frontend/           Next.js (App Router) + TypeScript + Tailwind + Recharts
  ml/                 Standalone training / experiment scripts
  data/               CSV samples + deterministic seed fixtures
  docs/               architecture, database, api, agent-design, test-plan
  tests/              Playwright end-to-end specs (backend unit tests live in backend/tests)
  docker/             Dockerfiles + compose helpers
  docker-compose.yml
```

## 2. What is real vs simulated

| Layer | Status |
|---|---|
| Dead-stock detection, KPIs, forecasts, agent math, recovery engine, guardrails, 3D rack risk | **Real computation** on database data |
| Inventory / sales / B2B buyers / stores | **Seeded demo data** (`backend/app/seed`, deterministic seed) |
| Execution (POS, transfers, B2B orders) | **Simulated execution** — writes to the database, no external calls |
| Outcome verification | **Prototype simulation** using the seeded demand model — explicitly labelled in the UI |
| LLM narration | **Optional**. Core decisions are deterministic; an LLM only ever rewrites explanations |

No dashboard number is hardcoded. Every KPI is derived from rows in the database.

## 3. Quick start (Docker, recommended)

```bash
cp .env.example .env
docker compose up --build
# API      http://localhost:8000/docs
# Frontend http://localhost:3000
```

The backend container waits for Postgres, runs `alembic upgrade head`, seeds the demo
dataset (idempotent), then serves the API.

## 4. Quick start (local, without Docker)

**Postgres is required for the application.** Tests use SQLite in-memory as a fallback so
the pure-logic layer can run in CI without a database.

```bash
# --- backend ---
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg://stockmind:stockmind@localhost:5432/stockmind"
alembic upgrade head
python -m app.seed.seed            # idempotent deterministic seed
uvicorn app.main:app --reload      # http://localhost:8000

# --- frontend ---
cd ../frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev                        # http://localhost:3000
```

## 5. Demo accounts

| Email | Password | Role |
|---|---|---|
| `manager@stockmind.demo` | `demo1234` | Store Manager |
| `inventory@stockmind.demo` | `demo1234` | Inventory Staff |

## 6. Making a judge run

1. Log in.
2. **Dead Stock Center** — browse the detected dead-stock SKUs (filter by store, category, risk).
3. Open a SKU → **Product Detail** (aging explanation + forecast).
4. **Recovery Studio** → *Analyze Recovery* → four agent proposals side by side.
5. Read the recommended plan, then **Execute Plan** (simulated execution writes to the DB).
6. Watch the timeline, before/after metrics and audit trail update from real rows.
7. **3D Warehouse** — rack colours derived from real risk; click a shelf to read its SKUs.
8. **Judge Demo Mode** — one deterministic scenario end-to-end, no manual steps.

Frontend routes: `/login`, `/dashboard`, `/dead-stock`, `/products/[id]`, `/recovery-studio`,
`/warehouse`, `/stores`, `/b2b`, `/history`, `/import`, `/demo`.

## 7. API

OpenAPI is served at `/docs`. REST surface:

```
GET  /api/health
GET  /api/dashboard
GET  /api/inventory
GET  /api/dead-stock
GET  /api/products/{id}
GET  /api/products/{id}/forecast
GET  /api/products/{id}/recovery-options
POST /api/recovery/analyze
POST /api/recovery/execute
GET  /api/recovery/history
GET  /api/stores
GET  /api/b2b-buyers
POST /api/import/csv
POST /api/agents/discount
POST /api/agents/inter-store-swap
POST /api/agents/buy-a-get-b
POST /api/agents/b2b
```

## 8. Documentation

* [`docs/architecture.md`](docs/architecture.md)
* [`docs/database.md`](docs/database.md)
* [`docs/api.md`](docs/api.md)
* [`docs/agent-design.md`](docs/agent-design.md)
* [`docs/test-plan.md`](docs/test-plan.md)

## 9. Tests

```bash
cd backend && pytest -q          # pure-logic unit suite (runs without Postgres)
cd frontend && npm run lint && npm run typecheck
cd tests && npx playwright test  # requires the stack to be running
```
