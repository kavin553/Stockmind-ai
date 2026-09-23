"use client";

import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import { CheckCircle2, Loader2, Play, ShieldCheck, Sparkles, XCircle, Zap } from "lucide-react";
import { api } from "@/lib/api";
import {
  AGENT_LABELS,
  AGENT_SHORT,
  GUARDRAIL_STYLES,
  RISK_STYLES,
  TRIGGER_LABELS,
  money,
  number,
  percent,
  signedPercent,
  timeLabel,
} from "@/lib/format";
import type { AgentKey, AnalyzeResponse, DeadStockRow, DemoRunResponse, ExecuteResponse, TimelineEvent } from "@/lib/types";
import { Badge, Card, EmptyState, ErrorState, PrototypeSimulationNote, SectionTitle, Skeleton } from "@/components/ui";
import { RecoveryComparisonBar } from "@/components/charts";

type Params = { productId: string | null; store: string | null; demo: boolean };

export default function RecoveryStudioPage() {
  const [params, setParams] = useState<Params>({ productId: null, store: null, demo: false });
  const [candidates, setCandidates] = useState<DeadStockRow[]>([]);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [demo, setDemo] = useState<DemoRunResponse | null>(null);
  const [execution, setExecution] = useState<ExecuteResponse | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const search = new URLSearchParams(window.location.search);
    setParams({
      productId: search.get("product_id"),
      store: search.get("store"),
      demo: search.get("demo") === "1",
    });
    api
      .deadStock()
      .then((page) => setCandidates(page.items))
      .catch(() => setCandidates([]));
  }, []);

  const runAnalyze = useCallback(async (productId: string, store: string) => {
    setLoading(true);
    setError(null);
    setNotice(null);
    setExecution(null);
    setDemo(null);
    try {
      const response = await api.analyze(productId, store);
      setAnalysis(response);
      setTimeline([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed.");
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const runDemo = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const response = await api.demoRun();
      setDemo(response);
      setAnalysis({
        case: response.case,
        metrics: response.metrics,
        forecast: response.forecast,
        agent_results: response.agent_results,
        plan: response.plan,
      });
      setExecution(response.execution);
      setTimeline(response.timeline);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Autonomous run failed.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!params.productId && !params.demo) return;
    if (params.demo) {
      void runDemo();
    } else if (params.productId && params.store) {
      void runAnalyze(params.productId, params.store);
    }
  }, [params, runAnalyze, runDemo]);

  async function execute() {
    if (!analysis) return;
    setExecuting(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api.execute(analysis.plan.id, `ui-${Date.now()}`);
      setExecution(result);
      const events = await api.timeline(analysis.plan.id);
      setTimeline(events.events);
      setNotice("Plan executed. Inventory, promotions and the audit trail were updated in the database.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Execution failed.");
    } finally {
      setExecuting(false);
    }
  }

  const agentResults = analysis?.agent_results ?? [];
  const comparison = agentResults.map((result) => ({
    name: AGENT_SHORT[result.agent],
    gross: result.feasible ? result.expected_recovery : 0,
    net: result.feasible ? result.expected_net_recovery : 0,
  }));

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-50">
            <Sparkles className="h-5 w-5 text-accent-cyan" aria-hidden />
            Recovery Studio
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Four specialized agents compete on <strong className="text-slate-300">expected net recovery</strong> — not
            raw revenue. The engine may also split one SKU into a hybrid plan when that recovers more.
          </p>
        </div>
        <button
          type="button"
          onClick={runDemo}
          disabled={loading}
          className="focus-ring inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-accent-cyan to-accent-blue px-4 py-2 text-sm font-semibold text-base-900 hover:opacity-90 disabled:opacity-60"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Zap className="h-4 w-4" aria-hidden />}
          Run Autonomous Recovery
        </button>
      </header>

      <Card>
        <SectionTitle title="Select a dead-stock SKU" subtitle="Or start from the Dead Stock Center." />
        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-[320px] flex-1">
            <span className="label-caps">Candidate</span>
            <select
              value={params.productId && params.store ? `${params.productId}|${params.store}` : ""}
              onChange={(event) => {
                const [productId, store] = event.target.value.split("|");
                setParams({ productId, store, demo: false });
              }}
              className="focus-ring mt-1 block w-full rounded-lg border border-base-600 bg-base-900/60 px-3 py-2 text-sm text-slate-100"
            >
              <option value="">Choose a dead-stock SKU…</option>
              {candidates.map((row) => (
                <option key={`${row.product_id}-${row.store_id}`} value={`${row.product_id}|${row.store}`}>
                  {row.sku} — {row.name.slice(0, 40)} · {row.store} · {money(row.capital_locked)} locked
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={!params.productId || !params.store || loading}
            onClick={() => params.productId && params.store && runAnalyze(params.productId, params.store)}
            className="focus-ring inline-flex items-center gap-2 rounded-lg border border-accent-cyan/50 px-4 py-2 text-sm font-medium text-accent-cyan hover:bg-accent-cyan/10 disabled:opacity-40"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
            Analyze Recovery
          </button>
        </div>
      </Card>

      {error ? <ErrorState message={error} /> : null}
      {notice ? (
        <div className="flex items-start gap-2 rounded-lg border border-signal-success/40 bg-signal-success/10 p-3 text-xs text-signal-success">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>{notice}</span>
        </div>
      ) : null}
      {loading && !analysis ? <Skeleton className="h-96" /> : null}

      {!analysis && !loading ? (
        <EmptyState
          title="No SKU analyzed yet"
          description="Pick a candidate above, or run the autonomous demo to watch the full detect → evaluate → recover → verify loop."
        />
      ) : null}

      {analysis ? (
        <>
          {/* CURRENT STATE */}
          <Card>
            <SectionTitle
              title="Current state"
              subtitle="Detected from real inventory and sales rows."
              action={<Badge className={RISK_STYLES[analysis.metrics.risk_band]}>{analysis.metrics.risk_band.replace("_", " ")}</Badge>}
            />
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
              {[
                { label: "Stock", value: number(analysis.case.stock_units) },
                { label: "Inventory age", value: `${number(analysis.metrics.age_days)} d` },
                { label: "Days since sale", value: `${number(analysis.metrics.days_since_sale)} d` },
                { label: "30-day forecast", value: number(analysis.forecast.forecast_30d, 1) },
                { label: "Excess units", value: number(analysis.metrics.excess_units, 0) },
                { label: "Capital locked", value: money(analysis.metrics.capital_locked) },
                { label: "Risk score", value: percent(analysis.metrics.risk_score, 0) },
              ].map((item) => (
                <div key={item.label} className="rounded-lg border border-base-600/60 bg-base-900/40 p-3">
                  <p className="label-caps">{item.label}</p>
                  <p className="mt-1 font-mono text-lg text-slate-100">{item.value}</p>
                </div>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="label-caps">Triggers</span>
              {analysis.metrics.triggers.map((trigger) => (
                <Badge key={trigger} className="border-signal-critical/40 bg-signal-critical/10 text-signal-critical">
                  {TRIGGER_LABELS[trigger] ?? trigger}
                </Badge>
              ))}
              <span className="ml-auto text-[11px] text-slate-500">
                Forecast method <span className="font-mono text-slate-400">{analysis.forecast.method}</span> · confidence{" "}
                <span className="font-mono text-slate-400">{percent(analysis.forecast.confidence, 0)}</span>
              </span>
            </div>
            <p className="mt-3 text-xs leading-relaxed text-slate-400">{buildNarrative(analysis)}</p>
          </Card>

          {/* FOUR AGENT OPTIONS */}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {analysis.agent_results.map((result) => {
              const selected = analysis.plan.allocations.some((allocation) => allocation.agent === result.agent);
              return (
                <Card
                  key={result.agent}
                  className={clsx("flex flex-col", selected ? "border-accent-cyan/60 shadow-glow" : "")}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-slate-100">{AGENT_LABELS[result.agent]}</p>
                      <p className="mt-0.5 text-[11px] text-slate-500">
                        Confidence {result.feasible ? percent(result.confidence, 0) : "—"}
                      </p>
                    </div>
                    {result.feasible ? (
                      <Badge className="border-signal-success/40 bg-signal-success/10 text-signal-success">
                        <CheckCircle2 className="h-3 w-3" aria-hidden /> Feasible
                      </Badge>
                    ) : (
                      <Badge className="border-signal-critical/40 bg-signal-critical/10 text-signal-critical">
                        <XCircle className="h-3 w-3" aria-hidden /> Not feasible
                      </Badge>
                    )}
                  </div>

                  {result.feasible ? (
                    <>
                      <dl className="mt-4 space-y-2 text-xs">
                        <Row label="Units cleared" value={number(result.expected_units_cleared, 0)} />
                        <Row label="Expected recovery" value={money(result.expected_recovery)} />
                        <Row label="Expected loss" value={money(result.expected_loss)} />
                        <Row label="Action cost" value={money(result.action_cost)} />
                        <Row
                          label="Expected net recovery"
                          value={money(result.expected_net_recovery)}
                          emphasis={selected}
                        />
                      </dl>
                      <ul className="mt-4 space-y-2 text-[11px] leading-relaxed text-slate-400">
                        {result.reasons.slice(0, 3).map((reason) => (
                          <li key={reason} className="border-l border-base-500 pl-2">
                            {reason}
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <p className="mt-4 text-xs leading-relaxed text-slate-400">{result.reason_unavailable}</p>
                  )}

                  {selected ? (
                    <p className="mt-4 border-t border-base-600/60 pt-2 text-[11px] font-medium text-accent-cyan">
                      Included in the recommended plan
                    </p>
                  ) : null}
                </Card>
              );
            })}
          </div>

          {/* COMPARISON */}
          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <SectionTitle title="Recovery comparison" subtitle="Gross recovery vs expected net recovery (costs, friction and risk deducted)" />
              <RecoveryComparisonBar data={comparison} />
            </Card>

            <Card>
              <SectionTitle
                title="AI-selected recovery plan"
                subtitle={`${analysis.plan.strategy === "hybrid" ? "Hybrid" : "Single"} strategy`}
                action={<Badge className={GUARDRAIL_STYLES[analysis.plan.guardrail_status]}>Guardrails: {analysis.plan.guardrail_status}</Badge>}
              />
              <p className="text-xs leading-relaxed text-slate-300">{analysis.plan.explanation}</p>

              <div className="mt-4 space-y-2">
                {analysis.plan.allocations.map((allocation) => (
                  <div
                    key={allocation.agent}
                    className="flex items-center justify-between rounded-lg border border-base-600/60 bg-base-900/40 px-3 py-2"
                  >
                    <div>
                      <p className="text-xs font-medium text-slate-200">{AGENT_LABELS[allocation.agent as AgentKey]}</p>
                      <p className="text-[11px] text-slate-500">
                        {number(allocation.units)} units · cost {money(allocation.action_cost)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-sm text-signal-success">{money(allocation.expected_net_recovery)}</p>
                      <p className="text-[11px] text-slate-500">net recovery</p>
                    </div>
                  </div>
                ))}
                {analysis.plan.allocations.length === 0 ? (
                  <p className="rounded-lg border border-signal-critical/40 bg-signal-critical/10 p-3 text-xs text-signal-critical">
                    No acceptable recovery path. The plan is intentionally empty rather than loss-making.
                  </p>
                ) : null}
              </div>

              <dl className="mt-4 grid grid-cols-3 gap-3 text-xs">
                <div className="rounded-lg border border-base-600/60 bg-base-900/40 p-3">
                  <dt className="label-caps">Gross</dt>
                  <dd className="mt-1 font-mono text-sm text-slate-100">{money(analysis.plan.expected_recovery)}</dd>
                </div>
                <div className="rounded-lg border border-base-600/60 bg-base-900/40 p-3">
                  <dt className="label-caps">Action cost</dt>
                  <dd className="mt-1 font-mono text-sm text-slate-100">{money(analysis.plan.total_action_cost)}</dd>
                </div>
                <div className="rounded-lg border border-accent-cyan/40 bg-accent-cyan/5 p-3">
                  <dt className="label-caps">Net recovery</dt>
                  <dd className="mt-1 font-mono text-sm text-accent-cyan">{money(analysis.plan.expected_net_recovery)}</dd>
                </div>
              </dl>

              {analysis.plan.guardrail_findings.length > 0 ? (
                <div className="mt-4 space-y-1.5">
                  {analysis.plan.guardrail_findings.map((finding, index) => (
                    <div
                      key={`${finding.code}-${index}`}
                      className={clsx(
                        "rounded-md border px-3 py-2 text-[11px]",
                        finding.severity === "block"
                          ? "border-signal-critical/40 bg-signal-critical/10 text-signal-critical"
                          : finding.severity === "flag"
                            ? "border-signal-warning/40 bg-signal-warning/10 text-signal-warning"
                            : "border-base-600/60 bg-base-900/40 text-slate-400",
                      )}
                    >
                      {finding.message}
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="mt-5 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={execute}
                  disabled={
                    executing ||
                    analysis.plan.guardrail_status === "blocked" ||
                    analysis.plan.allocations.length === 0 ||
                    Boolean(execution)
                  }
                  className="focus-ring inline-flex items-center gap-2 rounded-lg bg-signal-success px-4 py-2 text-sm font-semibold text-base-900 hover:opacity-90 disabled:opacity-40"
                >
                  {executing ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <ShieldCheck className="h-4 w-4" aria-hidden />}
                  {execution ? "Executed" : "Execute Plan"}
                </button>
                <PrototypeSimulationNote />
              </div>
            </Card>
          </div>

          {/* BEFORE / AFTER */}
          {execution ? (
            <Card>
              <SectionTitle
                title="Before / after"
                subtitle="Read back from the database after execution — not animated."
                action={<Badge className="border-signal-success/40 bg-signal-success/10 text-signal-success">Prototype Simulation</Badge>}
              />
              <div className="grid gap-4 md:grid-cols-3">
                <MetricCompare label="Units on hand" before={execution.before.quantity} after={execution.after.quantity} />
                <MetricCompare
                  label="Capital locked"
                  before={money(execution.before.capital_locked)}
                  after={money(execution.after.capital_locked)}
                  moneyMode
                />
                <MetricCompare
                  label="Discount applied"
                  before={percent(execution.before.discount_pct, 0)}
                  after={percent(execution.after.discount_pct, 0)}
                />
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-3 text-xs md:grid-cols-4">
                <PredictedActual label="Units cleared" predicted={execution.verification.predicted_units} simulated={execution.verification.simulated_units} />
                <PredictedActual
                  label="Recovery"
                  predicted={money(execution.verification.predicted_recovery)}
                  simulated={money(execution.verification.simulated_recovery)}
                />
                <div className="rounded-lg border border-base-600/60 bg-base-900/40 p-3">
                  <p className="label-caps">Units variance</p>
                  <p className="mt-1 font-mono text-sm text-slate-100">{signedPercent(execution.verification.units_variance_pct)}</p>
                </div>
                <div className="rounded-lg border border-base-600/60 bg-base-900/40 p-3">
                  <p className="label-caps">Recovery variance</p>
                  <p className="mt-1 font-mono text-sm text-slate-100">{signedPercent(execution.verification.recovery_variance_pct)}</p>
                </div>
              </dl>
            </Card>
          ) : null}

          {/* TIMELINE */}
          {timeline.length > 0 ? (
            <Card>
              <SectionTitle title="Execution timeline" subtitle="Generated from stored events and audit rows" />
              <ol className="relative space-y-3 border-l border-base-600/60 pl-5">
                {timeline.map((event, index) => (
                  <li key={`${event.event}-${index}`} className="relative">
                    <span className="absolute -left-[26px] top-1 h-2.5 w-2.5 rounded-full bg-accent-cyan" />
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="font-mono text-[11px] text-slate-500">{timeLabel(event.at)}</span>
                      <span className="text-xs text-slate-200">{event.message}</span>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          ) : null}

          {demo ? (
            <Card>
              <SectionTitle title="Autonomous run summary" subtitle={`Scenario: ${demo.scenario} · ${demo.product.sku} @ ${demo.store}`} />
              <div className="grid grid-cols-2 gap-3 text-xs md:grid-cols-4">
                <Summary label="Agents evaluated" value={String(demo.agent_results.length)} />
                <Summary label="Strategy" value={demo.plan.strategy} />
                <Summary label="Units cleared" value={number(demo.execution.units_cleared)} />
                <Summary label="Net recovery" value={money(demo.plan.expected_net_recovery)} />
              </div>
            </Card>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function Row({ label, value, emphasis }: { label: string; value: string; emphasis?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-slate-500">{label}</dt>
      <dd className={clsx("font-mono tabular-nums", emphasis ? "text-accent-cyan" : "text-slate-200")}>{value}</dd>
    </div>
  );
}

function MetricCompare({
  label,
  before,
  after,
  moneyMode,
}: {
  label: string;
  before: string | number;
  after: string | number;
  moneyMode?: boolean;
}) {
  const numericBefore = typeof before === "number" ? before : 0;
  const numericAfter = typeof after === "number" ? after : 0;
  const improved = !moneyMode ? numericAfter < numericBefore : numericAfter < numericBefore;
  return (
    <div className="rounded-lg border border-base-600/60 bg-base-900/40 p-4">
      <p className="label-caps">{label}</p>
      <div className="mt-2 flex items-baseline gap-3">
        <span className="font-mono text-lg text-slate-400 line-through">{before}</span>
        <span className="text-slate-600">→</span>
        <span className={clsx("font-mono text-lg", improved ? "text-signal-success" : "text-slate-100")}>{after}</span>
      </div>
    </div>
  );
}

function PredictedActual({ label, predicted, simulated }: { label: string; predicted: string | number; simulated: string | number }) {
  return (
    <div className="rounded-lg border border-base-600/60 bg-base-900/40 p-3">
      <p className="label-caps">{label}</p>
      <div className="mt-1 flex items-center justify-between text-xs">
        <span className="text-slate-500">Predicted</span>
        <span className="font-mono text-slate-200">{predicted}</span>
      </div>
      <div className="mt-1 flex items-center justify-between text-xs">
        <span className="text-slate-500">Simulated</span>
        <span className="font-mono text-slate-200">{simulated}</span>
      </div>
    </div>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-base-600/60 bg-base-900/40 p-3">
      <p className="label-caps">{label}</p>
      <p className="mt-1 font-mono text-sm capitalize text-slate-100">{value}</p>
    </div>
  );
}

/** Narrative built strictly from the returned numbers. */
function buildNarrative(analysis: AnalyzeResponse): string {
  const { metrics, forecast, plan } = analysis;
  const ratio = forecast.forecast_30d > 0 ? metrics.excess_ratio : null;
  const winner = plan.allocations[0];
  const parts = [
    `This SKU has been in stock for ${metrics.age_days} days and has not sold for ${metrics.days_since_sale} days.`,
  ];
  if (ratio !== null) {
    parts.push(`Current stock is ${ratio.toFixed(1)}× predicted 30-day demand (${forecast.forecast_30d.toFixed(1)} units).`);
  } else {
    parts.push("Predicted 30-day demand is effectively zero, so holding this stock recovers nothing.");
  }
  if (winner) {
    parts.push(
      `The ${plan.strategy} plan selected ${AGENT_LABELS[winner.agent]} for ${winner.units} units, projecting ` +
        `${money(plan.expected_net_recovery)} of net recovery against ${money(metrics.capital_locked)} of locked capital.`,
    );
  } else {
    parts.push("No strategy beat the policy floor, so no recovery plan was recommended.");
  }
  return parts.join(" ");
}
