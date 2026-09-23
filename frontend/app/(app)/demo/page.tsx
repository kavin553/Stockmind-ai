"use client";

import { useState } from "react";
import { CheckCircle2, CircleDashed, GitCompareArrows, Loader2, PlayCircle, Trophy } from "lucide-react";
import { api } from "@/lib/api";
import { AGENT_LABELS, AGENT_SHORT, GUARDRAIL_STYLES, RISK_STYLES, money, number, percent, signedPercent, timeLabel } from "@/lib/format";
import type { DemoRunResponse } from "@/lib/types";
import { Badge, Card, EmptyState, ErrorState, PrototypeSimulationNote, SectionTitle } from "@/components/ui";
import { RecoveryComparisonBar } from "@/components/charts";

const STEPS = [
  { id: "detect", label: "Dead-stock case detected" },
  { id: "agents", label: "Four agents evaluate the opportunity" },
  { id: "compare", label: "Recovery engine compares expected net recovery" },
  { id: "guardrail", label: "Guardrails validate the plan" },
  { id: "execute", label: "Simulated action executed against the database" },
  { id: "verify", label: "Outcome verified (prototype simulation)" },
  { id: "audit", label: "Audit trail written" },
];

export default function JudgeDemoPage() {
  const [run, setRun] = useState<DemoRunResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setLoading(true);
    setError(null);
    setRun(null);
    try {
      setRun(await api.demoRun());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Autonomous run failed.");
    } finally {
      setLoading(false);
    }
  }

  const comparison = (run?.agent_results ?? []).map((result) => ({
    name: AGENT_SHORT[result.agent],
    gross: result.feasible ? result.expected_recovery : 0,
    net: result.feasible ? result.expected_net_recovery : 0,
  }));

  const completed = new Set<string>();
  if (run) {
    completed.add("detect");
    if (run.agent_results.length) completed.add("agents");
    if (run.plan) completed.add("compare");
    if (run.plan.guardrail_status) completed.add("guardrail");
    if (run.execution) completed.add("execute");
    if (run.execution?.verification) completed.add("verify");
    if (run.timeline.some((event) => event.event.startsWith("audit_"))) completed.add("audit");
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-50">
            <Trophy className="h-5 w-5 text-accent-cyan" aria-hidden />
            Judge Demo Mode
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            One deterministic scenario, end to end: detect a dead-stock case, run all four agents, compare expected net
            recovery, apply guardrails, execute the simulated action and verify the outcome. No manual steps.
          </p>
        </div>
        <button
          type="button"
          onClick={start}
          disabled={loading}
          className="focus-ring inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-accent-cyan to-accent-blue px-5 py-2.5 text-sm font-semibold text-base-900 hover:opacity-90 disabled:opacity-60"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <PlayCircle className="h-4 w-4" aria-hidden />}
          Run Autonomous Recovery
        </button>
      </header>

      {error ? <ErrorState message={error} onRetry={start} /> : null}

      <div className="grid gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        <Card>
          <SectionTitle title="Process" subtitle="Live state of the autonomous run" />
          <ol className="space-y-3">
            {STEPS.map((step) => {
              const done = completed.has(step.id);
              const active = loading && !done;
              return (
                <li key={step.id} className="flex items-start gap-3">
                  {done ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-signal-success" aria-hidden />
                  ) : (
                    <CircleDashed
                      className={`mt-0.5 h-4 w-4 shrink-0 ${active ? "animate-spin text-accent-cyan" : "text-slate-600"}`}
                      aria-hidden
                    />
                  )}
                  <span className={`text-xs ${done ? "text-slate-200" : "text-slate-500"}`}>{step.label}</span>
                </li>
              );
            })}
          </ol>
          <PrototypeSimulationNote className="mt-4" />
        </Card>

        <div className="space-y-4">
          {!run && !loading ? (
            <EmptyState
              title="Ready to run"
              description="Press Run Autonomous Recovery. The run picks the highest-priority dead-stock candidate from the seeded database and recovers it without further input."
            />
          ) : null}

          {run ? (
            <>
              <Card>
                <SectionTitle
                  title={`${run.product.sku} — ${run.product.name}`}
                  subtitle={`${run.store} · ${run.plan.strategy} strategy · scenario "${run.scenario}"`}
                  action={<Badge className={RISK_STYLES[run.metrics.risk_band]}>{run.metrics.risk_band.replace("_", " ")}</Badge>}
                />
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  {[
                    { label: "Stock cleared", value: number(run.execution.units_cleared) },
                    { label: "Expected net recovery", value: money(run.plan.expected_net_recovery) },
                    { label: "Capital freed", value: money(run.execution.before.capital_locked - run.execution.after.capital_locked) },
                    { label: "Guardrails", value: run.plan.guardrail_status },
                  ].map((item) => (
                    <div key={item.label} className="rounded-lg border border-base-600/60 bg-base-900/40 p-3">
                      <p className="label-caps">{item.label}</p>
                      <p className="mt-1 font-mono text-sm capitalize text-slate-100">{item.value}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-xs leading-relaxed text-slate-400">{run.plan.explanation}</p>
              </Card>

              <Card>
                <SectionTitle title="Agent comparison" subtitle="The four agents evaluated the same structured input" />
                <RecoveryComparisonBar data={comparison} />
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  {run.agent_results.map((result) => {
                    const selected = run.plan.allocations.some((allocation) => allocation.agent === result.agent);
                    return (
                      <div
                        key={result.agent}
                        className={`rounded-lg border p-3 ${selected ? "border-accent-cyan/50 bg-accent-cyan/5" : "border-base-600/60 bg-base-900/40"}`}
                      >
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-medium text-slate-200">{AGENT_LABELS[result.agent]}</p>
                          {selected ? (
                            <Badge className="border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan">selected</Badge>
                          ) : null}
                        </div>
                        {result.feasible ? (
                          <p className="mt-1 font-mono text-[11px] text-slate-400">
                            net {money(result.expected_net_recovery)} · {number(result.expected_units_cleared)} units · conf{" "}
                            {percent(result.confidence, 0)}
                          </p>
                        ) : (
                          <p className="mt-1 text-[11px] text-slate-500">Not feasible — {result.reason_unavailable}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Card>

              <Card>
                <SectionTitle
                  title="Before / after (database)"
                  subtitle="Read straight back from the database after execution"
                  action={<Badge className={GUARDRAIL_STYLES[run.plan.guardrail_status]}>{run.plan.guardrail_status}</Badge>}
                />
                <div className="grid gap-3 md:grid-cols-3">
                  <Delta label="Units on hand" before={number(run.execution.before.quantity)} after={number(run.execution.after.quantity)} />
                  <Delta
                    label="Capital locked"
                    before={money(run.execution.before.capital_locked)}
                    after={money(run.execution.after.capital_locked)}
                  />
                  <Delta
                    label="Recovery variance"
                    before={money(run.execution.verification.predicted_recovery)}
                    after={money(run.execution.verification.simulated_recovery)}
                    hint={signedPercent(run.execution.verification.recovery_variance_pct)}
                  />
                </div>
              </Card>

              <Card>
                <SectionTitle title="Execution timeline" subtitle="Every event comes from stored rows and audit entries" />
                <ol className="relative space-y-3 border-l border-base-600/60 pl-5">
                  {run.timeline.map((event, index) => (
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
            </>
          ) : null}
        </div>
      </div>

      <p className="flex items-center gap-2 text-[11px] text-slate-600">
        <GitCompareArrows className="h-3.5 w-3.5" aria-hidden />
        The scenario is deterministic: the same seed always produces the same starting state, and the same run always
        produces the same events.
      </p>
    </div>
  );
}

function Delta({ label, before, after, hint }: { label: string; before: string; after: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-base-600/60 bg-base-900/40 p-4">
      <p className="label-caps">{label}</p>
      <div className="mt-2 flex items-baseline gap-3">
        <span className="font-mono text-base text-slate-400 line-through">{before}</span>
        <span className="text-slate-600">→</span>
        <span className="font-mono text-base text-signal-success">{after}</span>
      </div>
      {hint ? <p className="mt-1 font-mono text-[11px] text-slate-500">{hint}</p> : null}
    </div>
  );
}
