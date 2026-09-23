"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { Filter, Search, Sparkles, TriangleAlert } from "lucide-react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { AGENT_SHORT, GUARDRAIL_STYLES, RISK_STYLES, TRIGGER_LABELS, money, number, percent } from "@/lib/format";
import type { DeadStockRow, RiskBand } from "@/lib/types";
import { Badge, Card, EmptyState, ErrorState, Skeleton } from "@/components/ui";

const RISK_OPTIONS: (RiskBand | "")[] = ["", "critical", "at_risk", "watch", "healthy"];

export default function DeadStockCenterPage() {
  const [store, setStore] = useState("");
  const [risk, setRisk] = useState<RiskBand | "">("");
  const [query, setQuery] = useState("");
  const [minAge, setMinAge] = useState("");
  const [sortKey, setSortKey] = useState<keyof DeadStockRow>("capital_locked");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");

  const loader = useCallback(
    () => api.deadStock({ store: store || undefined, risk: risk || undefined, min_age: minAge ? Number(minAge) : undefined }),
    [store, risk, minAge],
  );
  const { data, loading, error, reload } = useAsync(loader, [store, risk, minAge]);

  const rows = useMemo(() => {
    const items = data?.items ?? [];
    const filtered = query
      ? items.filter(
          (row) =>
            row.sku.toLowerCase().includes(query.toLowerCase()) ||
            row.name.toLowerCase().includes(query.toLowerCase()),
        )
      : items;
    const key = sortKey;
    return [...filtered].sort((a, b) => {
      const left = (a[key] ?? 0) as number | string;
      const right = (b[key] ?? 0) as number | string;
      if (typeof left === "string" || typeof right === "string") {
        return direction === "asc"
          ? String(left).localeCompare(String(right))
          : String(right).localeCompare(String(left));
      }
      return direction === "asc" ? left - right : right - left;
    });
  }, [data, query, sortKey, direction]);

  function toggleSort(key: keyof DeadStockRow) {
    if (key === sortKey) setDirection(direction === "asc" ? "desc" : "asc");
    else {
      setSortKey(key);
      setDirection("desc");
    }
  }

  const stores = Array.from(new Set((data?.items ?? []).map((row) => row.store))).sort();
  const totalLocked = rows.reduce((sum, row) => sum + row.capital_locked, 0);
  const totalRecoverable = rows.reduce((sum, row) => sum + (row.expected_net_recovery ?? 0), 0);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-50">
          <TriangleAlert className="h-5 w-5 text-signal-critical" aria-hidden />
          Dead Stock Center
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Every row is a detected recovery candidate. Low stock is never listed here — low stock is a replenishment
          problem, not a recovery problem.
        </p>
      </header>

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-[200px] flex-1">
            <span className="label-caps">Search</span>
            <span className="mt-1 flex items-center gap-2 rounded-lg border border-base-600 bg-base-900/60 px-3 py-2">
              <Search className="h-3.5 w-3.5 text-slate-500" aria-hidden />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="SKU or product name"
                className="w-full bg-transparent text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none"
              />
            </span>
          </label>

          <label>
            <span className="label-caps">Store</span>
            <select
              value={store}
              onChange={(event) => setStore(event.target.value)}
              className="focus-ring mt-1 block w-44 rounded-lg border border-base-600 bg-base-900/60 px-3 py-2 text-sm text-slate-100"
            >
              <option value="">All stores</option>
              {stores.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span className="label-caps">Risk band</span>
            <select
              value={risk}
              onChange={(event) => setRisk(event.target.value as RiskBand | "")}
              className="focus-ring mt-1 block w-40 rounded-lg border border-base-600 bg-base-900/60 px-3 py-2 text-sm text-slate-100"
            >
              {RISK_OPTIONS.map((option) => (
                <option key={option || "all"} value={option}>
                  {option ? option.replace("_", " ") : "All risks"}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span className="label-caps">Min age (days)</span>
            <input
              type="number"
              min={0}
              value={minAge}
              onChange={(event) => setMinAge(event.target.value)}
              placeholder="e.g. 90"
              className="focus-ring mt-1 block w-32 rounded-lg border border-base-600 bg-base-900/60 px-3 py-2 text-sm text-slate-100"
            />
          </label>

          <div className="ml-auto flex items-center gap-3 text-xs text-slate-400">
            <Filter className="h-3.5 w-3.5 text-slate-500" aria-hidden />
            <span>
              <strong className="font-mono text-slate-200">{rows.length}</strong> candidates
            </span>
            <span className="text-slate-600">|</span>
            <span>
              Locked <strong className="font-mono text-signal-critical">{money(totalLocked)}</strong>
            </span>
            <span className="text-slate-600">|</span>
            <span>
              Recoverable <strong className="font-mono text-signal-success">{money(totalRecoverable)}</strong>
            </span>
          </div>
        </div>
      </Card>

      {loading && !data ? <Skeleton className="h-96" /> : null}
      {error ? <ErrorState message={error} onRetry={reload} /> : null}

      {data && rows.length === 0 ? (
        <EmptyState
          title="No dead-stock candidates match these filters"
          description="Try clearing the filters. If nothing is listed at all, run the seed to load the demo dataset."
        />
      ) : null}

      {data && rows.length > 0 ? (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[1200px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-base-600/70 text-left">
                {(
                  [
                    ["sku", "SKU"],
                    ["name", "Product"],
                    ["store", "Store"],
                    ["quantity", "Stock"],
                    ["age_days", "Age"],
                    ["days_since_sale", "Days Since Sale"],
                    ["forecast_30d", "30-Day Forecast"],
                    ["risk_score", "Dead Stock Risk"],
                    ["capital_locked", "Capital Locked"],
                    ["best_strategy", "Best Recovery Strategy"],
                    ["expected_net_recovery", "Expected Net Recovery"],
                  ] as [keyof DeadStockRow, string][]
                ).map(([key, label]) => (
                  <th
                    key={key}
                    scope="col"
                    onClick={() => toggleSort(key)}
                    className="cursor-pointer whitespace-nowrap px-4 py-3 label-caps hover:text-accent-cyan"
                  >
                    {label}
                    {sortKey === key ? <span className="ml-1 text-accent-cyan">{direction === "asc" ? "▲" : "▼"}</span> : null}
                  </th>
                ))}
                <th scope="col" className="px-4 py-3 label-caps">
                  Action
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.product_id}-${row.store_id}`} className="border-b border-base-700/50 hover:bg-base-700/30">
                  <td className="px-4 py-3 font-mono text-xs text-slate-200">{row.sku}</td>
                  <td className="max-w-[220px] truncate px-4 py-3 text-slate-300" title={row.name}>
                    {row.name}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">{row.store}</td>
                  <td className="px-4 py-3 font-mono tabular-nums text-slate-200">{number(row.quantity)}</td>
                  <td className="px-4 py-3 font-mono tabular-nums text-slate-300">{number(row.age_days)}d</td>
                  <td className="px-4 py-3 font-mono tabular-nums text-slate-300">{number(row.days_since_sale)}d</td>
                  <td className="px-4 py-3 font-mono tabular-nums text-slate-300">{number(row.forecast_30d, 1)}</td>
                  <td className="px-4 py-3">
                    <Badge className={RISK_STYLES[row.risk_band]} title={row.triggers.map((t) => TRIGGER_LABELS[t] ?? t).join(", ")}>
                      {row.risk_band.replace("_", " ")} · {percent(row.risk_score, 0)}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 font-mono tabular-nums text-slate-200">{money(row.capital_locked)}</td>
                  <td className="px-4 py-3">
                    {row.best_strategy ? (
                      <div className="flex items-center gap-2">
                        <Badge className="border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan">
                          {AGENT_SHORT[row.best_strategy]}
                        </Badge>
                        {row.guardrail_status ? (
                          <Badge className={GUARDRAIL_STYLES[row.guardrail_status]}>{row.guardrail_status}</Badge>
                        ) : null}
                      </div>
                    ) : (
                      <span className="text-xs text-slate-500">Not analyzed</span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono tabular-nums text-signal-success">
                    {row.expected_net_recovery === null ? "—" : money(row.expected_net_recovery)}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/recovery-studio?product_id=${row.product_id}&store=${row.store}`}
                      className="focus-ring inline-flex items-center gap-1 rounded-md border border-accent-cyan/40 px-2.5 py-1 text-[11px] font-medium text-accent-cyan hover:bg-accent-cyan/10"
                    >
                      <Sparkles className="h-3 w-3" aria-hidden /> Analyze
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : null}
    </div>
  );
}
