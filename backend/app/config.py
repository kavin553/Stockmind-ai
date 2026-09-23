"""Application configuration and the deterministic policy/threshold model.

Every tunable business constant lives here (or in the ``settings`` DB table, which is
seeded from these defaults) so that no business rule is buried in a route handler.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, overridable via environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "StockMind AI"
    version: str = "0.5.0"
    environment: Literal["dev", "test", "prod"] = "dev"

    # Postgres is the application database. Tests may override with SQLite.
    database_url: str = Field(
        default="postgresql+psycopg://stockmind:stockmind@localhost:5432/stockmind",
        alias="DATABASE_URL",
    )
    sql_echo: bool = False

    # Local demo auth
    secret_key: str = "stockmind-demo-secret-change-me"
    token_ttl_minutes: int = 720

    cors_origins: str = "http://localhost:3000"

    # Optional LLM narration. When unset, the deterministic explainer is used.
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"


class Policy(BaseSettings):
    """Configurable business thresholds. Mirrors the ``settings`` table."""

    model_config = SettingsConfigDict(env_prefix="STOCKMIND_", extra="ignore")

    # --- dead-stock detection -------------------------------------------------
    aging_days: int = 60
    no_sale_days: int = 30
    excess_stock_multiplier: float = 2.5
    velocity_decline_ratio: float = 0.4  # recent velocity vs. long-run velocity
    velocity_decline_min_history_days: int = 14

    # --- risk scoring ---------------------------------------------------------
    risk_aging_days: int = 180     # age at which the aging sub-score saturates
    risk_no_sale_days: int = 90    # days-since-sale at which that sub-score saturates
    risk_excess_ratio: float = 4.0  # stock/forecast ratio at which excess saturates
    risk_bands: dict[str, float] = {
        "healthy": 0.25,
        "watch": 0.45,
        "at_risk": 0.70,
        "critical": 1.01,
    }
    capital_at_risk_factor: float = 0.55  # fraction of locked capital considered at risk

    # --- discount agent -------------------------------------------------------
    discount_candidates: list[float] = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    min_margin_pct: float = 0.08          # margin over unit cost that must survive
    max_handling_discount: float = 0.45   # beyond this, dead stock is written down

    # --- inter-store swap agent ----------------------------------------------
    transfer_base_handling: float = 12.0      # currency per unit
    transfer_rate_per_km: float = 1.6         # currency per unit per km
    transfer_max_units: int = 500
    transfer_min_units: int = 5
    transfer_avoided_markdown_pct: float = 0.20  # markdown the source would otherwise need

    # --- buy-a-get-b agent ----------------------------------------------------
    min_bundle_compatibility: float = 0.45
    min_anchor_demand: float = 20.0
    base_attach_rate: float = 0.18
    reduced_price_factor: float = 0.60   # B at 40% off
    max_anchor_candidates: int = 5

    # --- B2B buyer agent ------------------------------------------------------
    b2b_price_floor_pct: float = 0.80    # fraction of unit cost that is the floor
    b2b_target_price_factor: float = 0.75  # ask at most 75% of list
    b2b_min_match_score: float = 0.35

    # --- recovery engine ------------------------------------------------------
    default_horizon_days: int = 30
    friction_cost_ratio: dict[str, float] = {
        "discount": 0.010,
        "inter_store_swap": 0.035,
        "buy_a_get_b": 0.025,
        "b2b_bulk_buyer": 0.020,
    }
    risk_penalty_weight: float = 0.30
    hybrid_min_improvement: float = 0.03
    hybrid_weight_steps: list[float] = [0.25, 0.4, 0.5, 0.6, 0.75]
    min_acceptable_net_recovery: float = 0.0

    # --- guardrails -----------------------------------------------------------
    max_autonomous_discount: float = 0.20
    min_plan_net_recovery_ratio: float = 0.15  # of capital locked

    # --- forecasting ----------------------------------------------------------
    forecast_horizons: list[int] = [7, 30, 60]
    cold_start_min_sales_days: int = 21
    category_baseline_window_days: int = 90
    model_version: str = "xgb-v1"

    # --- verification ---------------------------------------------------------
    simulation_elasticity_damping: float = 0.85
    verification_label: str = "prototype_simulation"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_policy() -> Policy:
    return Policy()


settings = get_settings()
policy = get_policy()
