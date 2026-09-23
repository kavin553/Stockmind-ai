"""Pydantic contracts shared by the agents, services and API.

The agents are pure functions over these structures — they never touch the ORM. That is
what makes them independently unit-testable and safe to run concurrently.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AgentKey = Literal["discount", "inter_store_swap", "buy_a_get_b", "b2b_bulk_buyer"]
RiskBand = Literal["healthy", "watch", "at_risk", "critical"]
GuardrailStatus = Literal["passed", "flagged", "blocked"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- inputs


class ProductSpec(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    category: str
    category_id: uuid.UUID
    unit_cost: float = Field(ge=0)
    list_price: float = Field(gt=0)
    b2b_floor_pct: float = Field(gt=0, le=1)
    elasticity: float = 1.1
    dimensions_cm: dict | None = None


class StoreSpec(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    city: str
    lat: float | None = None
    lon: float | None = None


class InventorySpec(BaseModel):
    quantity: int = Field(ge=0)
    discount_pct: float = Field(ge=0, le=0.95)
    first_received_at: date
    last_sold_at: date | None = None
    location_code: str = "UNASSIGNED"


class InventoryMetrics(BaseModel):
    age_days: int
    days_since_sale: int
    sales_velocity_30d: float
    sales_velocity_90d: float
    velocity_decline: float  # 1 - (recent vs long-run); >0 means slowing
    excess_units: float
    excess_ratio: float  # stock / forecast_30d
    risk_score: float = Field(ge=0, le=1)
    risk_band: RiskBand
    capital_locked: float
    capital_at_risk: float
    triggers: list[str] = Field(default_factory=list)


class SalePoint(BaseModel):
    sold_on: date
    quantity: int
    unit_price: float
    is_promotion: bool = False


class ForecastBundle(BaseModel):
    forecast_7d: float = Field(ge=0)
    forecast_30d: float = Field(ge=0)
    forecast_60d: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    method: str
    as_of: date
    model_metrics: dict | None = None


class StoreDemand(BaseModel):
    """A candidate destination store for an inter-store transfer."""

    store: StoreSpec
    quantity_on_hand: int = Field(ge=0)
    forecast_7d: float = Field(ge=0)
    forecast_30d: float = Field(ge=0)
    forecast_confidence: float = Field(ge=0, le=1)
    current_discount_pct: float = Field(ge=0, le=0.95)
    distance_km: float = Field(ge=0)


class BundleCandidate(BaseModel):
    """A high-demand anchor product A that could carry dead-stock product B."""

    product: ProductSpec
    store_id: uuid.UUID
    quantity_on_hand: int = Field(ge=0)
    forecast_30d: float = Field(ge=0)
    forecast_confidence: float = Field(ge=0, le=1)
    current_discount_pct: float = Field(ge=0, le=0.95)
    category_affinity: float = Field(ge=0, le=1)
    co_purchase_rate: float = Field(ge=0, le=1)


class BuyerSpec(BaseModel):
    id: uuid.UUID
    business_name: str
    required_categories: list[str]
    location_city: str
    lat: float | None = None
    lon: float | None = None
    required_quantity: int = Field(gt=0)
    maximum_budget: float = Field(ge=0)
    preferred_unit_price: float = Field(ge=0)
    reliability_score: float = Field(ge=0, le=1)


class PolicySpec(BaseModel):
    """The subset of policy the agents need. Mirrors ``app.config.Policy``."""

    aging_days: int = 60
    no_sale_days: int = 30
    excess_stock_multiplier: float = 2.5
    min_margin_pct: float = 0.08
    discount_candidates: list[float] = Field(default_factory=lambda: [0.05, 0.10, 0.15, 0.20, 0.25, 0.30])
    transfer_base_handling: float = 12.0
    transfer_rate_per_km: float = 1.6
    transfer_max_units: int = 500
    transfer_min_units: int = 5
    transfer_avoided_markdown_pct: float = 0.20
    min_bundle_compatibility: float = 0.45
    min_anchor_demand: float = 20.0
    base_attach_rate: float = 0.18
    reduced_price_factor: float = 0.60
    b2b_price_floor_pct: float = 0.80
    b2b_target_price_factor: float = 0.75
    b2b_min_match_score: float = 0.35
    max_anchor_candidates: int = 5
    max_autonomous_discount: float = 0.20
    min_plan_net_recovery_ratio: float = 0.15
    risk_penalty_weight: float = 0.30
    hybrid_weight_steps: list[float] = Field(default_factory=lambda: [0.25, 0.4, 0.5, 0.6, 0.75])
    hybrid_min_improvement: float = 0.03
    friction_cost_ratio: dict[str, float] = Field(
        default_factory=lambda: {
            "discount": 0.010,
            "inter_store_swap": 0.035,
            "buy_a_get_b": 0.025,
            "b2b_bulk_buyer": 0.020,
        }
    )


class RecoveryContext(BaseModel):
    """Everything an agent is allowed to see for one dead-stock case."""

    case_id: uuid.UUID | None = None
    product: ProductSpec
    store: StoreSpec
    inventory: InventorySpec
    metrics: InventoryMetrics
    forecast: ForecastBundle
    recent_sales: list[SalePoint] = Field(default_factory=list)
    previous_discounts: list[float] = Field(default_factory=list)
    peer_stores: list[StoreDemand] = Field(default_factory=list)
    bundle_candidates: list[BundleCandidate] = Field(default_factory=list)
    b2b_buyers: list[BuyerSpec] = Field(default_factory=list)
    policy: PolicySpec = Field(default_factory=PolicySpec)

    @property
    def available_units(self) -> int:
        return self.inventory.quantity


# --------------------------------------------------------------------------- outputs


class DiscountScenario(BaseModel):
    discount_pct: float
    predicted_units_cleared: float
    expected_revenue: float
    gross_margin: float
    remaining_stock: float
    expected_recovery: float
    expected_loss: float
    below_margin_floor: bool


class AgentResult(BaseModel):
    agent: AgentKey
    feasible: bool = False
    reason_unavailable: str | None = None
    expected_units_cleared: float = 0.0
    expected_recovery: float = 0.0
    expected_loss: float = 0.0
    action_cost: float = 0.0
    expected_net_recovery: float = 0.0
    confidence: float = Field(default=0.0, ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)

    @classmethod
    def infeasible(cls, agent: AgentKey, reason: str, **payload) -> "AgentResult":
        return cls(agent=agent, feasible=False, reason_unavailable=reason, payload=payload)


class PlanAllocation(BaseModel):
    agent: AgentKey
    units: int = Field(ge=0)
    expected_recovery: float = 0.0
    expected_net_recovery: float = 0.0
    action_cost: float = 0.0
    confidence: float = 0.0
    detail: dict = Field(default_factory=dict)


class GuardrailFinding(BaseModel):
    code: str
    severity: Literal["info", "flag", "block"]
    message: str
    agent: str | None = None


class RecoveryPlanDraft(BaseModel):
    case_id: uuid.UUID | None = None
    strategy: Literal["single", "hybrid"] = "single"
    allocations: list[PlanAllocation] = Field(default_factory=list)
    expected_recovery: float = 0.0
    expected_loss: float = 0.0
    total_action_cost: float = 0.0
    expected_net_recovery: float = 0.0
    confidence: float = 0.0
    guardrail_status: GuardrailStatus = "passed"
    guardrail_findings: list[GuardrailFinding] = Field(default_factory=list)
    explanation: str = ""

    @property
    def total_units(self) -> int:
        return sum(a.units for a in self.allocations)
