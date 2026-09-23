.PHONY: help up down logs migrate seed backend frontend test test-backend lint typecheck clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Start Postgres + backend + frontend with Docker Compose
	docker compose up --build

down: ## Stop everything
	docker compose down

logs: ## Tail all service logs
	docker compose logs -f

migrate: ## Apply Alembic migrations
	cd backend && alembic upgrade head

seed: ## Seed the deterministic demo dataset (idempotent)
	cd backend && python -m app.seed.seed

backend: ## Run the API locally (needs Postgres)
	cd backend && uvicorn app.main:app --reload --port 8000

frontend: ## Run the Next.js dev server
	cd frontend && npm run dev

test: test-backend ## Run the test suite

test-backend: ## Backend unit + API tests (no Postgres required)
	cd backend && pytest -q

lint: ## Lint the frontend
	cd frontend && npm run lint

typecheck: ## TypeScript type check
	cd frontend && npm run typecheck

clean: ## Remove Python caches
	find backend -type d -name __pycache__ -prune -exec rm -rf {} + || true
