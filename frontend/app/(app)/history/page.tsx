"use client";

import { useCallback } from "react";
import { ClipboardList } from "lucide-react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { AGENT_SHORT, GUARDRAIL_STYLES, money, number, signedPercent, timeLabel } from "@/lib/format";
import { Badge, Card, EmptyState, ErrorState, PrototypeSimulationNote, Skeleton } from "@/components/ui";

export default function ActionHistoryPage() {
  const { data, loading, error, reload } = useAsync(
    useCallback(() => api.history(), []),
    [],
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-50">
          <ClipboardList className="h-5 w-5 text-accent-blue" aria-hidden />
          Action History
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Every executed recovery action with its predicted vs simulated outcome. Outcomes are prototype simulations,
          not real-world measurements.
        </p>
      </header>

      {loading && !data ? <Skeleton className="h-96" /> : null}
      {error ? <ErrorState message={error} onRetry={reload} /> : null}

      {data && data.items.length === 0 ? (
        <EmptyState
          title="No recovery actions executed yet"
          description="Analyze a dead-stock SKU in the Recovery Studio and execute the recommended plan, or run the autonomous demo."
        />
      ) : null}

      {data && data.items.length > 0 ? (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[1100px] text-sm">
            <thead>
              <tr className="border-b border-base-600/70 text-left label-caps">
                <th className="px-4 py-3">When</th>
                <th className="px-4 py-3">SKU</th>
                <th className="px-4 py-3">Product</th>
                <th className="px-4 py-3">Store</th>
                <th className="px-4 py-3">Strategy</th>
                <th className="px-4 py-3">Units</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Guardrails</th>
                <th className="px-4 py-3">Predicted / Simulated</th>
                <th className="px-4 py-3">Variance</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => {
                const predicted = row.verification?.predicted_recovery;
                const simulated = row.verification?.simulated_recovery;
                const variance = row.verification?.recovery_variance_pct;
                return (
                  <tr key={row.action_id} className="border-b border-base-700/50 hover:bg-base-700/30">
                    <td className="px-4 py-3 font-mono text-[11px] text-slate-400">{timeLabel(row.executed_at)}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-200">{row.sku}</td>
                    <td className="max-w-[200px] truncate px-4 py-3 text-slate-300" title={row.name}>
                      {row.name}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-400">{row.store}</td>
                    <td className="px-4 py-3">
                      <Badge className="border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan">
                        {AGENT_SHORT[row.agent] ?? row.agent}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 font-mono tabular-nums text-slate-200">{number(row.units)}</td>
                    <td className="px-4 py-3 text-xs text-slate-300">{row.status}</td>
                    <td className="px-4 py-3">
                      <Badge className={GUARDRAIL_STYLES[row.guardrail_status]}>{row.guardrail_status}</Badge>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-300">
                      {typeof predicted === "number" ? money(predicted) : "—"} /{" "}
                      {typeof simulated === "number" ? money(simulated) : "—"}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-300">
                      {typeof variance === "number" ? signedPercent(variance) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      ) : null}

      <PrototypeSimulationNote />
    </div>
  );
}
