"use client";

import { useCallback } from "react";
import { ArrowRight, Network } from "lucide-react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { money, number } from "@/lib/format";
import { Badge, Card, EmptyState, ErrorState, SectionTitle, Skeleton } from "@/components/ui";

export default function StoreNetworkPage() {
  const stores = useAsync(
    useCallback(() => api.stores(), []),
    [],
  );
  const transfers = useAsync(
    useCallback(() => api.transferOpportunities(), []),
    [],
  );

  const maxValue = Math.max(1, ...(stores.data?.items ?? []).map((store) => store.inventory_value));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-50">
          <Network className="h-5 w-5 text-accent-blue" aria-hidden />
          Store Network
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Compare stock, demand and dead-stock exposure across stores, and see the transfer opportunities the
          Inter-Store Swap Agent has identified.
        </p>
      </header>

      {stores.error ? <ErrorState message={stores.error} onRetry={stores.reload} /> : null}
      {stores.loading && !stores.data ? (
        <Skeleton className="h-56" />
      ) : stores.data ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {stores.data.items.map((store) => (
            <Card key={store.id} className="space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-semibold text-slate-100">{store.name}</p>
                  <p className="font-mono text-[11px] text-slate-500">
                    {store.code} · {store.city}, {store.region}
                  </p>
                </div>
                <Badge className="border-accent-blue/40 bg-accent-blue/10 text-accent-blue">{number(store.units)} units</Badge>
              </div>

              <div>
                <div className="flex items-baseline justify-between text-xs">
                  <span className="text-slate-500">Inventory value</span>
                  <span className="font-mono text-slate-200">{money(store.inventory_value)}</span>
                </div>
                <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-base-700">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-accent-blue to-accent-cyan"
                    style={{ width: `${(store.inventory_value / maxValue) * 100}%` }}
                  />
                </div>
              </div>

              <dl className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-md border border-base-600/60 bg-base-900/40 p-2">
                  <dt className="text-slate-500">Dead stock value</dt>
                  <dd className="mt-0.5 font-mono text-signal-critical">{money(store.dead_stock_value)}</dd>
                </div>
                <div className="rounded-md border border-base-600/60 bg-base-900/40 p-2">
                  <dt className="text-slate-500">30-day demand</dt>
                  <dd className="mt-0.5 font-mono text-slate-200">{number(store.demand_30d, 0)}</dd>
                </div>
              </dl>
            </Card>
          ))}
        </div>
      ) : null}

      <Card>
        <SectionTitle
          title="Transfer opportunities"
          subtitle="Source → destination moves that recover more than they cost"
          action={
            transfers.data ? (
              <Badge className="border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan">
                {transfers.data.items.length} candidates
              </Badge>
            ) : null
          }
        />
        {transfers.error ? <ErrorState message={transfers.error} onRetry={transfers.reload} /> : null}
        {transfers.loading && !transfers.data ? <Skeleton className="h-48" /> : null}
        {transfers.data && transfers.data.items.length === 0 ? (
          <EmptyState
            title="No profitable transfers right now"
            description="A transfer is only proposed when a destination's demand beats its stock and the freight is smaller than the avoided markdown."
          />
        ) : null}
        {transfers.data && transfers.data.items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead>
                <tr className="border-b border-base-600/70 text-left label-caps">
                  <th className="px-3 py-2">SKU</th>
                  <th className="px-3 py-2">Product</th>
                  <th className="px-3 py-2">Route</th>
                  <th className="px-3 py-2">Distance</th>
                  <th className="px-3 py-2">Units</th>
                  <th className="px-3 py-2">Freight</th>
                  <th className="px-3 py-2">Recovery</th>
                  <th className="px-3 py-2">Net</th>
                </tr>
              </thead>
              <tbody>
                {transfers.data.items.slice(0, 40).map((item) => (
                  <tr key={`${item.product_id}-${item.destination_store}`} className="border-b border-base-700/50">
                    <td className="px-3 py-2 font-mono text-xs text-slate-200">{item.sku}</td>
                    <td className="max-w-[200px] truncate px-3 py-2 text-slate-300" title={item.name}>
                      {item.name}
                    </td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1 font-mono text-[11px] text-slate-300">
                        {item.source_store} <ArrowRight className="h-3 w-3 text-accent-cyan" aria-hidden /> {item.destination_store}
                      </span>
                      <span className="ml-2 text-[11px] text-slate-500">{item.destination_city}</span>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-400">{number(item.distance_km, 0)} km</td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-200">{number(item.quantity)}</td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-400">{money(item.transfer_cost)}</td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-200">{money(item.expected_recovery)}</td>
                    <td className="px-3 py-2 font-mono text-xs text-signal-success">{money(item.net)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
