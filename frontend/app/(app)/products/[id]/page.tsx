"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Boxes, PackageSearch, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { AGENT_SHORT, RISK_STYLES, TRIGGER_LABELS, dateLabel, money, number, percent } from "@/lib/format";
import type { AnalyzeResponse, ProductDetail } from "@/lib/types";
import { Badge, Card, EmptyState, ErrorState, PrototypeSimulationNote, SectionTitle, Skeleton } from "@/components/ui";
import { SalesTrendArea } from "@/components/charts";

export default function ProductDetailPage({ params }: { params: { id: string } }) {
  const [storeCode, setStoreCode] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  const loader = useCallback(() => api.product(params.id), [params.id]);
  const { data, loading, error, reload } = useAsync(loader, [params.id]);

  useEffect(() => {
    if (data && !storeCode && data.inventory.length > 0) setStoreCode(data.inventory[0].store);
  }, [data, storeCode]);

  const current = data?.inventory.find((entry) => entry.store === storeCode) ?? data?.inventory[0];

  async function analyze() {
    if (!current) return;
    setAnalyzing(true);
    try {
      setAnalysis(await api.analyze(params.id, current.store));
    } finally {
      setAnalyzing(false);
    }
  }

  if (loading && !data) return <Skeleton className="h-96" />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/dead-stock"
          className="focus-ring inline-flex items-center gap-1 rounded-md border border-base-600 px-2.5 py-1 text-xs text-slate-400 hover:text-accent-cyan"
        >
          <ArrowLeft className="h-3 w-3" aria-hidden /> Back
        </Link>
        <span className="font-mono text-xs text-slate-500">{data.product.sku}</span>
      </div>

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="rounded-lg border border-base-600 bg-base-900/60 p-2.5">
              <PackageSearch className="h-6 w-6 text-accent-blue" aria-hidden />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-slate-50">{data.product.name}</h1>
              <p className="mt-0.5 text-xs text-slate-500">
                {data.product.category} · cost {money(data.product.unit_cost)} · list {money(data.product.list_price)}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {data.inventory.map((entry) => (
              <button
                key={entry.store}
                type="button"
                onClick={() => setStoreCode(entry.store)}
                className={`focus-ring rounded-md border px-2.5 py-1 text-[11px] ${
                  entry.store === current?.store
                    ? "border-accent-cyan/50 bg-accent-cyan/10 text-accent-cyan"
                    : "border-base-600 text-slate-400 hover:text-slate-100"
                }`}
              >
                {entry.store}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {!current ? (
        <EmptyState title="No inventory rows for this product" description="This product is not stocked in any store." />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="On hand" value={number(current.quantity)} />
            <Stat label="Inventory age" value={`${number(current.metrics.age_days)} d`} />
            <Stat label="Days since sale" value={`${number(current.metrics.days_since_sale)} d`} />
            <Stat label="Capital locked" value={money(current.capital_locked)} />
            <Stat label="30-day forecast" value={number(current.forecast.forecast_30d, 1)} />
            <Stat label="Risk" value={`${current.metrics.risk_band.replace("_", " ")} (${percent(current.metrics.risk_score, 0)})`} />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <SectionTitle title="Sales trend" subtitle="Units sold per day over the last 180 days" />
              <SalesTrendArea data={current.sales_history} />
            </Card>

            <Card>
              <SectionTitle title="Demand forecast" subtitle={`Method: ${current.forecast.method}`} />
              <div className="space-y-3 text-xs">
                <ForecastRow label="Next 7 days" value={current.forecast.forecast_7d} />
                <ForecastRow label="Next 30 days" value={current.forecast.forecast_30d} />
                <ForecastRow label="Next 60 days" value={current.forecast.forecast_60d} />
                <div className="flex items-center justify-between border-t border-base-600/60 pt-3">
                  <span className="text-slate-500">Confidence</span>
                  <span className="font-mono text-slate-200">{percent(current.forecast.confidence, 0)}</span>
                </div>
                {current.forecast.model_metrics ? (
                  <div className="rounded-lg border border-base-600/60 bg-base-900/40 p-3">
                    <p className="label-caps">Holdout metrics</p>
                    <div className="mt-2 space-y-1 font-mono text-[11px] text-slate-400">
                      {Object.entries(current.forecast.model_metrics).map(([key, value]) => (
                        <div key={key} className="flex justify-between">
                          <span>{key}</span>
                          <span className="text-slate-200">{typeof value === "number" ? value.toFixed(3) : String(value)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </Card>
          </div>

          <Card>
            <SectionTitle
              title="Dead-stock explanation"
              subtitle="Why the engine considers this SKU a recovery candidate"
              action={<Badge className={RISK_STYLES[current.metrics.risk_band]}>{current.metrics.risk_band.replace("_", " ")}</Badge>}
            />
            <div className="flex flex-wrap gap-2">
              {current.metrics.triggers.length ? (
                current.metrics.triggers.map((trigger) => (
                  <Badge key={trigger} className="border-signal-critical/40 bg-signal-critical/10 text-signal-critical">
                    {TRIGGER_LABELS[trigger] ?? trigger}
                  </Badge>
                ))
              ) : (
                <p className="text-xs text-slate-400">
                  No dead-stock trigger fires for this SKU at this store — it is not a recovery candidate.
                </p>
              )}
            </div>
            <p className="mt-3 text-xs leading-relaxed text-slate-400">
              Received {dateLabel(current.first_received_at)}, last sold {dateLabel(current.last_sold_at)}. Stock is{" "}
              {current.metrics.excess_units.toFixed(0)} units above the excess threshold (
              {current.metrics.excess_ratio.toFixed(1)}× predicted 30-day demand). Triggers evaluate ageing, days since
              sale, surplus versus forecast, and velocity decline.
            </p>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={analyze}
                disabled={analyzing}
                className="focus-ring inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-accent-cyan to-accent-blue px-4 py-2 text-sm font-semibold text-base-900 hover:opacity-90 disabled:opacity-60"
              >
                <Sparkles className="h-4 w-4" aria-hidden />
                {analyzing ? "Analyzing…" : "Analyze Recovery"}
              </button>
              <Link
                href={`/recovery-studio?product_id=${data.product.id}&store=${current.store}`}
                className="focus-ring inline-flex items-center gap-1 rounded-lg border border-base-600 px-3 py-2 text-xs text-slate-300 hover:border-accent-cyan/40 hover:text-accent-cyan"
              >
                Open in Recovery Studio
              </Link>
            </div>
          </Card>

          {analysis ? (
            <Card>
              <SectionTitle title="Agent evaluations" subtitle="Each agent computed independently over the same structured input" />
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {analysis.agent_results.map((result) => (
                  <div key={result.agent} className="rounded-lg border border-base-600/60 bg-base-900/40 p-3">
                    <p className="text-xs font-semibold text-slate-200">{AGENT_SHORT[result.agent]}</p>
                    {result.feasible ? (
                      <dl className="mt-2 space-y-1 text-[11px]">
                        <div className="flex justify-between">
                          <dt className="text-slate-500">Net recovery</dt>
                          <dd className="font-mono text-signal-success">{money(result.expected_net_recovery)}</dd>
                        </div>
                        <div className="flex justify-between">
                          <dt className="text-slate-500">Units</dt>
                          <dd className="font-mono text-slate-300">{number(result.expected_units_cleared)}</dd>
                        </div>
                        <div className="flex justify-between">
                          <dt className="text-slate-500">Confidence</dt>
                          <dd className="font-mono text-slate-300">{percent(result.confidence, 0)}</dd>
                        </div>
                      </dl>
                    ) : (
                      <p className="mt-2 text-[11px] text-slate-500">{result.reason_unavailable}</p>
                    )}
                  </div>
                ))}
              </div>
              <p className="mt-4 text-xs text-slate-400">{analysis.plan.explanation}</p>
              <PrototypeSimulationNote className="mt-2" />
            </Card>
          ) : null}
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel p-3">
      <p className="label-caps">{label}</p>
      <p className="mt-1 font-mono text-lg text-slate-100">{value}</p>
    </div>
  );
}

function ForecastRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono text-slate-200">{number(value, 1)} units</span>
    </div>
  );
}
