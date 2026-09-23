from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import settings

DESCRIPTION = """
**StockMind AI — Multi-Agent Dead Stock Recovery Platform.**

Detect dead stock, then let four specialized agents (Discount, Inter-Store Swap, Buy-A-Get-B,
B2B Bulk Buyer) compete on **expected net recovery** to find the cheapest way to clear it.

Every number returned by this API is computed from database rows or from a documented formula.
"""

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "health": "/api/health",
    }


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})
