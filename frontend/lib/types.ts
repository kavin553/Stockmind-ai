/** Shared API types. These mirror the FastAPI response shapes in docs/api.md. */

export type RiskBand = "healthy" | "watch" | "at_risk" | "critical";
export type GuardrailStatus = "passed" | "flagged" | "blocked" | "pending";
export type AgentKey = "discount" | "inter_store_swap" | "buy_a_get_b" | "b2b_bulk_buyer";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "store_manager" | "inventory_staff";
  store_id: string | null;
}

export interface DashboardKpis {
  current_inventory_value: number;
  dead_stock_value: number;
  dead_stock_units: number;
  dead_stock_pct: number;
  capital_locked: number;
  capital_at_risk: number;
  avg_inventory_age_days: number;
  critical_skus: number;
  recovery_rate: number;
  storage_volume_m3: number;
  dead_stock_storage_m3: number;
}

export interface DashboardResponse {
  kpis: DashboardKpis;
  charts: {
    dead_stock_by_category: { category: string; value: number }[];
    aging_buckets: { bucket: string; count: number }[];
    strategy_distribution: { strategy: string; count: number }[];
    capital_at_risk_series: { label: string; value: number }[];
    forecast_vs_actual: { label: string; forecast: number; actual: number }[];
  };
  generated_at: string;
}

export interface DeadStockRow {
  product_id: string;
  store_id: string;
  sku: string;
  name: string;
  category: string;
  store: string;
  quantity: number;
  age_days: number;
  days_since_sale: number;
  forecast_30d: number;
  risk_band: RiskBand;
  risk_score: number;
  capital_locked: number;
  capital_at_risk: number;
  excess_units: number;
  triggers: string[];
  best_strategy: AgentKey | null;
  strategy_type?: "single" | "hybrid" | null;
  expected_recovery: number | null;
  expected_net_recovery: number | null;
  guardrail_status: GuardrailStatus | null;
}

export interface Metrics {
  age_days: number;
  days_since_sale: number;
  sales_velocity_30d: number;
  sales_velocity_90d: number;
  velocity_decline: number;
  excess_units: number;
  excess_ratio: number;
  risk_score: number;
  risk_band: RiskBand;
  capital_locked: number;
  capital_at_risk: number;
  triggers: string[];
}

export interface Forecast {
  forecast_7d: number;
  forecast_30d: number;
  forecast_60d: number;
  confidence: number;
  method: string;
  as_of: string;
  model_metrics: Record<string, number> | null;
}

export interface AgentResultPayload {
  agent: AgentKey;
  label: string;
  feasible: boolean;
  reason_unavailable: string | null;
  expected_units_cleared: number;
  expected_recovery: number;
  expected_loss: number;
  action_cost: number;
  expected_net_recovery: number;
  confidence: number;
  reasons: string[];
  payload: Record<string, unknown>;
}

export interface PlanAllocation {
  agent: AgentKey;
  units: number;
  expected_recovery: number;
  expected_net_recovery: number;
  action_cost: number;
  confidence: number;
  detail: Record<string, unknown>;
}

export interface Plan {
  id: string;
  case_id: string;
  strategy: "single" | "hybrid";
  allocations: PlanAllocation[];
  expected_recovery: number;
  expected_loss: number;
  total_action_cost: number;
  expected_net_recovery: number;
  confidence: number;
  guardrail_status: GuardrailStatus;
  guardrail_findings: { code: string; severity: "info" | "flag" | "block"; message: string; agent: string | null }[];
  explanation: string;
  status: string;
  created_at: string | null;
}

export interface RecoveryCase {
  id: string;
  product_id: string;
  store_id: string;
  status: string;
  triggers: string[];
  age_days: number;
  days_since_sale: number;
  forecast_30d: number;
  excess_units: number;
  stock_units: number;
  capital_locked: number;
  capital_at_risk: number;
  risk_score: number;
  risk_band: RiskBand;
  detected_at: string | null;
}

export interface AnalyzeResponse {
  case: RecoveryCase;
  metrics: Metrics;
  forecast: Forecast;
  agent_results: AgentResultPayload[];
  plan: Plan;
}

export interface TimelineEvent {
  at: string;
  event: string;
  message: string;
  detail: Record<string, unknown>;
}

export interface ExecuteResponse {
  plan_id: string;
  case_id: string;
  actions: { id: string; agent: string; units: number; status: string; replayed?: boolean }[];
  before: { quantity: number; discount_pct: number; capital_locked: number };
  after: { quantity: number; discount_pct: number; capital_locked: number };
  units_cleared: number;
  verification: {
    predicted_units: number;
    simulated_units: number;
    predicted_recovery: number;
    simulated_recovery: number;
    units_variance_pct: number;
    recovery_variance_pct: number;
    label: string;
  };
}

export interface HistoryRow {
  action_id: string;
  sku: string;
  name: string;
  store: string;
  agent: AgentKey;
  label: string;
  units: number;
  status: string;
  executed_at: string | null;
  guardrail_status: GuardrailStatus;
  expected_net_recovery: number;
  verification: Record<string, number | string> | null;
}

export interface StoreRow {
  id: string;
  code: string;
  name: string;
  city: string;
  region: string;
  lat: number | null;
  lon: number | null;
  inventory_value: number;
  dead_stock_value: number;
  units: number;
  demand_30d: number;
}

export interface BuyerRow {
  id: string;
  business_name: string;
  required_categories: string[];
  location_city: string;
  required_quantity: number;
  maximum_budget: number;
  preferred_unit_price: number;
  reliability_score: number;
  matched_dead_stock_value: number;
}

export interface TransferOpportunity {
  product_id: string;
  sku: string;
  name: string;
  source_store: string;
  destination_store: string;
  destination_city: string;
  distance_km: number;
  quantity: number;
  transfer_cost: number;
  expected_recovery: number;
  net: number;
}

export interface ProductDetail {
  product: {
    id: string;
    sku: string;
    name: string;
    category: string;
    unit_cost: number;
    list_price: number;
    b2b_floor_pct: number;
    dimensions_cm: Record<string, number> | null;
  };
  inventory: {
    store_id: string;
    store: string;
    store_name: string;
    quantity: number;
    discount_pct: number;
    location_code: string;
    first_received_at: string;
    last_sold_at: string | null;
    capital_locked: number;
    metrics: Metrics;
    forecast: Forecast;
    sales_history: { date: string; quantity: number; unit_price: number; is_promotion: boolean }[];
    is_recovery_candidate: boolean;
  }[];
}

export interface DemoRunResponse {
  scenario: string;
  case: RecoveryCase;
  product: { sku: string; name: string };
  store: string;
  metrics: Metrics;
  forecast: Forecast;
  agent_results: AgentResultPayload[];
  plan: Plan;
  execution: ExecuteResponse;
  timeline: TimelineEvent[];
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface WarehouseItem {
  product_id: string;
  store_id: string;
  sku: string;
  name: string;
  quantity: number;
  unit_cost: number;
  capital_locked: number;
  risk_score: number;
  risk_band: RiskBand;
  age_days: number;
  days_since_sale: number;
  forecast_30d: number;
  is_recovery_candidate: boolean;
}

export interface WarehouseShelf {
  location_code: string;
  shelf: string;
  unit_count: number;
  total_units: number;
  total_value: number;
  risk_score: number;
  risk_band: RiskBand;
  recovery_candidates: number;
  items: WarehouseItem[];
}

export interface WarehouseRack {
  id: string;
  shelf_count: number;
  total_units: number;
  total_value: number;
  risk_score: number;
  risk_band: RiskBand;
  shelves: WarehouseShelf[];
}

export interface WarehouseLayout {
  store: { id: string; code: string; name: string; city: string } | null;
  racks: WarehouseRack[];
  generated_at: string;
}
