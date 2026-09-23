from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import agents, auth_routes, dashboard, health, inventory, network, recovery, warehouse

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(auth_routes.router)
api_router.include_router(dashboard.router)
api_router.include_router(inventory.router)
api_router.include_router(recovery.router)
api_router.include_router(agents.router)
api_router.include_router(network.router)
api_router.include_router(warehouse.router)
