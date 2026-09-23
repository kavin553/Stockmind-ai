"use client";

import { useCallback } from "react";
import { Building2, Store, Truck } from "lucide-react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { money, number, percent } from "@/lib/format";
import { Badge, Card, EmptyState, ErrorState, SectionTitle, Skeleton } from "@/components/ui";

export default function B2BMarketPage() {
  const buyers = useAsync(
    useCallback(() => api.buyers(), []),
    [],
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-50">
          <Building2 className="h-5 w-5 text-accent-blue" aria-hidden />
          B2B Market
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Bulk buyers registered in the demo marketplace. The B2B Bulk Buyer Agent scores each one on category fit,
          quantity, price compatibility, urgency, distance and reliability.
        </p>
      </header>

      {buyers.error ? <ErrorState message={buyers.error} onRetry={buyers.reload} /> : null}
      {buyers.loading && !buyers.data ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-48" />
          ))}
        </div>
      ) : null}

      {buyers.data && buyers.data.items.length === 0 ? (
        <EmptyState title="No buyers registered" description="Seed the demo dataset to populate the B2B marketplace." />
      ) : null}

      {buyers.data && buyers.data.items.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {buyers.data.items.map((buyer) => (
            <Card key={buyer.id} className="space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-2">
                  <div className="rounded-md border border-base-600 bg-base-900/60 p-1.5">
                    <Store className="h-4 w-4 text-accent-blue" aria-hidden />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-100">{buyer.business_name}</p>
                    <p className="text-[11px] text-slate-500">{buyer.location_city}</p>
                  </div>
                </div>
                <Badge className="border-signal-success/40 bg-signal-success/10 text-signal-success">
                  {percent(buyer.reliability_score, 0)} reliable
                </Badge>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {buyer.required_categories.map((category) => (
                  <Badge key={category} className="border-accent-cyan/30 bg-accent-cyan/5 text-accent-cyan">
                    {category}
                  </Badge>
                ))}
              </div>

              <dl className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-md border border-base-600/60 bg-base-900/40 p-2">
                  <dt className="text-slate-500">Minimum lot</dt>
                  <dd className="mt-0.5 font-mono text-slate-200">{number(buyer.required_quantity)} units</dd>
                </div>
                <div className="rounded-md border border-base-600/60 bg-base-900/40 p-2">
                  <dt className="text-slate-500">Budget</dt>
                  <dd className="mt-0.5 font-mono text-slate-200">{money(buyer.maximum_budget)}</dd>
                </div>
                <div className="rounded-md border border-base-600/60 bg-base-900/40 p-2">
                  <dt className="text-slate-500">Preferred price</dt>
                  <dd className="mt-0.5 font-mono text-slate-200">{money(buyer.preferred_unit_price)}</dd>
                </div>
                <div className="rounded-md border border-base-600/60 bg-base-900/40 p-2">
                  <dt className="text-slate-500">Matched dead stock</dt>
                  <dd className="mt-0.5 font-mono text-signal-success">{money(buyer.matched_dead_stock_value)}</dd>
                </div>
              </dl>
            </Card>
          ))}
        </div>
      ) : null}

      <Card>
        <SectionTitle title="How a bulk deal is evaluated" subtitle="Deterministic matching, no fabricated numbers" />
        <ul className="space-y-2 text-xs text-slate-400">
          {[
            "Category match — the buyer must actually purchase the product's category.",
            "Quantity fit — how closely the available stock matches the buyer's minimum lot.",
            "Price compatibility — the buyer's preferred price against the product's cost floor.",
            "Urgency — the dead-stock risk score, so the most stuck inventory is prioritised.",
            "Proximity — distance from the holding store; closer buyers keep more of the value.",
            "Reliability — the buyer's historical reliability score from the marketplace.",
          ].map((item) => (
            <li key={item} className="flex items-start gap-2">
              <Truck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-blue" aria-hidden />
              {item}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
