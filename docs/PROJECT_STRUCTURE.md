# StockMind AI — Project Structure

```
stockmind-ai/
├── README.md                     Project overview, quick start, API surface
├── Makefile                      up / down / migrate / seed / backend / frontend / test / lint
├── docker-compose.yml            Postgres 16 + backend + frontend
├── .env.example                  Every environment variable, with the policy overrides
├── .gitignore
│
├── backend/                      FastAPI · SQLAlchemy 2.0 · Alembic · XGBoost
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/cfb103bf54c2_initial_schema.py   # 19 tables
│   ├── app/
│   │   ├── main.py               FastAPI app, CORS, exception handling
│   │   ├── config.py             Settings + the complete policy/threshold model
│   │   ├── database.py           Engine / session / session_scope
│   │   ├── auth.py               PBKDF2 hashing + HMAC tokens (stdlib only)
│   │   ├── models/
│   │   │   ├── base.py           DeclarativeBase, UUID pk, timestamps
│   │   │   ├── catalog.py        users, stores, categories, products, inventory, sales
│   │   │   ├── recovery.py       forecasts, cases, agent_results, plans, actions,
│   │   │   │                     action_results, verification, promotions, transfers,
│   │   │   │                     audit_logs, settings
│   │   │   └── b2b.py            b2b_buyers, b2b_orders
│   │   ├── schemas/domain.py     RecoveryContext, AgentResult, PolicySpec, plan contracts
│   │   ├── agents/               ★ THE FOUR AI AGENTS ★
│   │   │   ├── discount_agent.py
│   │   │   ├── inter_store_swap_agent.py
│   │   │   ├── buy_a_get_b_agent.py
│   │   │   └── b2b_bulk_buyer_agent.py
│   │   ├── services/             ordinary services, never described as agents
│   │   │   ├── dead_stock_service.py        detection, triggers, risk, KPIs
│   │   │   ├── demand_forecast_service.py   DB ↔ ML bridge, forecast persistence
│   │   │   ├── recovery_engine.py           orchestration, net recovery, single/hybrid
│   │   │   ├── guardrail_service.py         deterministic policy checks
│   │   │   ├── execution_service.py         simulated execution (real DB writes)
│   │   │   ├── verification_service.py      predicted vs simulated
│   │   │   ├── audit_service.py             append-only trail
│   │   │   ├── data_ingest_service.py       CSV validation + upsert
│   │   │   └── warehouse_service.py         rack/shelf risk for the 3D twin
│   │   ├── ml/
│   │   │   ├── features.py       rolling windows, no future leakage
│   │   │   └── forecast.py       XGBoost + time-ordered holdout + cold-start baseline
│   │   ├── api/
│   │   │   ├── deps.py           session + auth dependencies
│   │   │   ├── router.py         /api aggregation
│   │   │   └── routes/           health, auth, dashboard, inventory, recovery,
│   │   │                         agents, network, warehouse
│   │   └── seed/seed.py          deterministic demo dataset (5 scenarios)
│   └── tests/                    111 tests
│       ├── conftest.py           context factory + seeded SQLite fixtures
│       ├── test_dead_stock.py            test_discount_agent.py
│       ├── test_inter_store_swap_agent.py test_buy_a_get_b_agent.py
│       ├── test_b2b_agent.py              test_recovery_engine.py
│       ├── test_guardrails.py             test_verification.py
│       ├── test_forecast.py               test_import_csv.py
│       ├── test_warehouse.py              test_api.py
│
├── frontend/                     Next.js 14 App Router · TypeScript · Tailwind · Recharts · R3F
│   ├── package.json  tsconfig.json  next.config.mjs  postcss.config.mjs  tailwind.config.ts
│   ├── app/
│   │   ├── layout.tsx  globals.css  page.tsx
│   │   ├── login/page.tsx
│   │   └── (app)/
│   │       ├── layout.tsx                 AppShell (sidebar nav + session guard)
│   │       ├── dashboard/page.tsx         KPIs + 5 charts
│   │       ├── dead-stock/page.tsx        MAIN PAGE: filters, sortable table
│   │       ├── products/[id]/page.tsx     product detail, forecast, explanation
│   │       ├── recovery-studio/page.tsx   HERO: 4 agents, comparison, execute, timeline
│   │       ├── warehouse/page.tsx         3D digital twin (data-driven risk colours)
│   │       ├── stores/page.tsx            store network + transfer opportunities
│   │       ├── b2b/page.tsx               buyer marketplace
│   │       ├── history/page.tsx           executed actions + outcomes
│   │       ├── import/page.tsx            CSV upload with per-row validation report
│   │       └── demo/page.tsx              Judge Demo Mode
│   ├── components/
│   │   ├── AppShell.tsx          navigation, session, sign-out
│   │   ├── ui.tsx                Card, StatCard, Badge, Skeleton, Empty/Error states
│   │   ├── charts.tsx            Recharts wrappers
│   │   └── WarehouseScene.tsx    React Three Fiber scene
│   └── lib/  api.ts · format.ts · types.ts · useAsync.ts
│
├── ml/
│   ├── train_forecaster.py       offline evaluation, prints holdout sMAPE
│   └── README.md
│
├── data/
│   ├── README.md
│   └── samples/  sales_sample.csv · inventory_sample.csv
│
├── docs/
│   ├── architecture.md           layers, data flow, net-recovery model, 3D twin
│   ├── database.md               every table, column, invariant and index
│   ├── api.md                    REST surface + payloads
│   ├── agent-design.md           the four agents, inputs, math, outputs
│   ├── test-plan.md              test inventory and exit criteria
│   ├── phase-report.md           phases 0–12 status, tests run, 9 bugs fixed, limitations
│   └── DEMO.md                   the 5-minute judge script
│
└── tests/                        Playwright end-to-end
    ├── package.json  playwright.config.ts
    └── e2e/judge-workflow.spec.ts
```

## Reading order for a new engineer

1. `README.md` — what it is and how to run it.
2. `docs/architecture.md` — how the pieces fit.
3. `docs/agent-design.md` — the four agents and their maths.
4. `backend/app/config.py` — every tunable threshold in one place.
5. `backend/app/services/recovery_engine.py` — the orchestration and scoring core.
6. `frontend/app/(app)/recovery-studio/page.tsx` — the hero experience.
