"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Play, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { money, moneyCompact, number, percent } from "@/lib/format";
import { Card, ErrorState, SectionTitle, Skeleton, StatCard, Badge } from "@/components/ui";
import {
  AgingBucketsBar,
  CapitalAtRiskLine,
  DeadStockByCategoryBar,
  ForecastVsActualLine,
  StrategyDistributionPie,
} from "@/components/charts";

export default function DashboardPage() {
  const loader = useCallback(() => api.dashboard(), []);
  const { data, loading, error, reload } = useAsync(loader);
  const [runningDemo, setRunningDemo] = useState(false);

  if (loading && !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-72" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <Skeleton key={index} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-72" />
      </div>
    );
  }

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  const { kpis, charts } = data;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-50">Recovery Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">
            Dead stock detected from inventory ageing, sales velocity and forecast demand. All values computed from
            the database.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={reload}
            className="focus-ring inline-flex items-center gap-2 rounded-lg border border-base-600 px-3 py-2 text-xs font-medium text-slate-300 hover:border-accent-cyan/40 hover:text-accent-cyan"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Refresh
          </button>
          <button
            type="button"
            onClick={() => {
              setRunningDemo(true);
              window.location.href = "/recovery-studio?demo=1";
            }}
            className="focus-ring inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-accent-cyan to-accent-blue px-3 py-2 text-xs font-semibold text-base-900 hover:opacity-90"
          >
            <Play className="h-3.5 w-3.5" aria-hidden />
            {runningDemo ? "Opening…" : "Run Autonomous Recovery"}
          </button>
        </div>
      </header>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Dead Stock Value" value={money(kpis.dead_stock_value)} tone="critical" hint={`${number(kpis.dead_stock_units)} units`} />
        <StatCard label="Capital Locked" value={money(kpis.capital_locked)} hint="Cost basis of dead stock" />
        <StatCard label="Capital at Risk" value={money(kpis.capital_at_risk)} tone="critical" hint="Weighted by risk score" />
        <StatCard label="Dead Stock %" value={percent(kpis.dead_stock_pct)} tone="accent" hint="Share of inventory value" />
        <StatCard label="Critical SKUs" value={number(kpis.critical_skus)} tone="critical" hint="Highest risk band" />
        <StatCard label="Average Inventory Age" value={`${number(kpis.avg_inventory_age_days, 1)} d`} hint="Across all SKUs" />
        <StatCard label="Recovery Rate" value={percent(kpis.recovery_rate)} tone="success" hint="Cases executed / total" />
        <StatCard
          label="Storage in Dead Stock"
          value={`${number(kpis.dead_stock_storage_m3, 2)} m³`}
          hint={`of ${number(kpis.storage_volume_m3, 2)} m³ total`}
        />
      </div>

      <Card>
        <SectionTitle
          title="Dead Stock → Recovery"
          subtitle="The product revolves around one loop: detect, evaluate, recover, verify."
        />
        <div className="flex flex-wrap items-center gap-3 text-xs">
          {[
            { label: "DETECT", detail: `${number(kpis.critical_skus)} critical SKUs` },
            { label: "EVALUATE", detail: "4 agents × every candidate" },
            { label: "RECOVER", detail: moneyCompact(kpis.dead_stock_value) },
            { label: "VERIFY", detail: "Prototype simulation" },
          ].map((step, index, all) => (
            <div key={step.label} className="flex items-center gap-3">
              <div className="rounded-lg border border-accent-cyan/30 bg-accent-cyan/5 px-3 py-2">
                <p className="font-mono text-[11px] font-semibold tracking-wider text-accent-cyan">{step.label}</p>
                <p className="mt-0.5 text-[11px] text-slate-500">{step.detail}</p>
              </div>
              {index < all.length - 1 ? <span className="text-slate-600">→</span> : null}
            </div>
          ))}
          <Link
            href="/dead-stock"
            className="focus-ring ml-auto inline-flex items-center gap-1 rounded-md border border-base-600 px-3 py-2 text-[11px] text-slate-300 hover:border-accent-cyan/40 hover:text-accent-cyan"
          >
            Open Dead Stock Center <ArrowUpRight className="h-3 w-3" aria-hidden />
          </Link>
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <SectionTitle title="Dead-stock value by category" />
          <DeadStockByCategoryBar data={charts.dead_stock_by_category} />
        </Card>
        <Card>
          <SectionTitle title="Inventory aging" subtitle="SKU count per age bucket" />
          <AgingBucketsBar data={charts.aging_buckets} />
        </Card>
        <Card>
          <SectionTitle title="Recovery strategy distribution" subtitle="Feasible agent evaluations per strategy" />
          <StrategyDistributionPie data={charts.strategy_distribution} />
        </Card>
        <Card>
          <SectionTitle
            title="Capital at risk"
            subtitle="Value of aged stock over the last six months"
            action={<Badge className="border-signal-critical/40 bg-signal-critical/10 text-signal-critical">Exposure</Badge>}
          />
          <CapitalAtRiskLine data={charts.capital_at_risk_series} />
        </Card>
        <Card className="xl:col-span-2">
          <SectionTitle title="Forecast vs actual" subtitle="Stored 7-day forecasts against the units that followed" />
          <ForecastVsActualLine data={charts.forecast_vs_actual} />
        </Card>
      </div>

      <p className="text-[11px] text-slate-600">
        Dashboard generated {data.generated_at}. Inventory, sales and buyer data are seeded; execution is simulated and
        clearly labelled.
      </p>
    </div>
  );
}
