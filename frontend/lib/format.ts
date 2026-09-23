import type { AgentKey, GuardrailStatus, RiskBand } from "./types";

const currency = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });

export const money = (value: number | null | undefined): string =>
  value === null || value === undefined ? "—" : currency.format(value);

export const moneyCompact = (value: number | null | undefined): string =>
  value === null || value === undefined ? "—" : `₹${compact.format(value)}`;

export const number = (value: number | null | undefined, digits = 0): string =>
  value === null || value === undefined ? "—" : value.toLocaleString("en-IN", { maximumFractionDigits: digits });

export const percent = (value: number | null | undefined, digits = 1): string =>
  value === null || value === undefined ? "—" : `${(value * 100).toFixed(digits)}%`;

export const signedPercent = (value: number | null | undefined, digits = 1): string => {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(digits)}%`;
};

export const dateLabel = (value: string | null | undefined): string =>
  value ? new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";

export const timeLabel = (value: string | null | undefined): string =>
  value ? new Date(value).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";

export const AGENT_LABELS: Record<AgentKey, string> = {
  discount: "Discount Agent",
  inter_store_swap: "Inter-Store Swap Agent",
  buy_a_get_b: "Buy-A-Get-B Combo Agent",
  b2b_bulk_buyer: "B2B Bulk Buyer Agent",
};

export const AGENT_SHORT: Record<AgentKey, string> = {
  discount: "Discount",
  inter_store_swap: "Inter-Store Swap",
  buy_a_get_b: "Buy-A-Get-B",
  b2b_bulk_buyer: "B2B Bulk",
};

export const TRIGGER_LABELS: Record<string, string> = {
  aging: "Aging",
  no_sale: "No recent sale",
  excess: "Excess vs demand",
  velocity_decline: "Velocity decline",
};

export const RISK_STYLES: Record<RiskBand, string> = {
  healthy: "border-signal-success/40 bg-signal-success/10 text-signal-success",
  watch: "border-accent-blue/40 bg-accent-blue/10 text-accent-blue",
  at_risk: "border-signal-warning/40 bg-signal-warning/10 text-signal-warning",
  critical: "border-signal-critical/40 bg-signal-critical/10 text-signal-critical",
};

export const GUARDRAIL_STYLES: Record<GuardrailStatus, string> = {
  passed: "border-signal-success/40 bg-signal-success/10 text-signal-success",
  flagged: "border-signal-warning/40 bg-signal-warning/10 text-signal-warning",
  blocked: "border-signal-critical/40 bg-signal-critical/10 text-signal-critical",
  pending: "border-slate-500/40 bg-slate-500/10 text-slate-300",
};

export function riskColor(band: RiskBand): string {
  return {
    healthy: "#10B981",
    watch: "#4FACFE",
    at_risk: "#F59E0B",
    critical: "#EF4444",
  }[band];
}
