"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Boxes, Cuboid, MousePointerClick, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/useAsync";
import { RISK_STYLES, money, number, percent } from "@/lib/format";
import type { WarehouseShelf } from "@/lib/types";
import { Badge, Card, EmptyState, ErrorState, SectionTitle, Skeleton } from "@/components/ui";
import type { Selection } from "@/components/WarehouseScene";

// Three.js must not run during SSR.
const WarehouseScene = dynamic(() => import("@/components/WarehouseScene"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[520px] items-center justify-center rounded-lg border border-base-600 text-xs text-slate-500">
      Loading 3D warehouse…
    </div>
  ),
});

export default function WarehousePage() {
  const [store, setStore] = useState<string>("");
  const [selection, setSelection] = useState<Selection | null>(null);

  const stores = useAsync(
    useCallback(() => api.stores(), []),
    [],
  );
  const layout = useAsync(
    useCallback(() => api.warehouse(store || undefined), [store]),
    [store],
  );

  useEffect(() => {
    if (!store && stores.data && stores.data.items.length > 0) setStore(stores.data.items[0].code);
  }, [stores.data, store]);

  const selectedShelf: WarehouseShelf | null = (() => {
    if (!selection || !layout.data) return null;
    for (const rack of layout.data.racks) {
      for (const shelf of rack.shelves) {
        if (shelf.location_code === selection.locationCode) return shelf;
      }
    }
    return null;
  })();

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-50">
            <Cuboid className="h-5 w-5 text-accent-cyan" aria-hidden />
            3D Digital Twin
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Rack and shelf colours are computed from real inventory risk — never hardcoded. Click a shelf to read the
            actual database rows stored there.
          </p>
        </div>
        <label>
          <span className="label-caps">Store</span>
          <select
            value={store}
            onChange={(event) => {
              setStore(event.target.value);
              setSelection(null);
            }}
            className="focus-ring mt-1 block w-52 rounded-lg border border-base-600 bg-base-900/60 px-3 py-2 text-sm text-slate-100"
          >
            {(stores.data?.items ?? []).map((entry) => (
              <option key={entry.id} value={entry.code}>
                {entry.code} · {entry.name}
              </option>
            ))}
          </select>
        </label>
      </header>

      <Card>
        <div className="flex flex-wrap items-center gap-4 text-xs">
          <span className="label-caps">Risk legend</span>
          {[
            { label: "Healthy", className: RISK_STYLES.healthy },
            { label: "Watch", className: RISK_STYLES.watch },
            { label: "At risk", className: RISK_STYLES.at_risk },
            { label: "Dead stock", className: RISK_STYLES.critical },
          ].map((item) => (
            <Badge key={item.label} className={item.className}>
              {item.label}
            </Badge>
          ))}
          <span className="ml-auto inline-flex items-center gap-1.5 text-slate-500">
            <MousePointerClick className="h-3.5 w-3.5" aria-hidden /> Drag to orbit · scroll to zoom · click a shelf
          </span>
        </div>
      </Card>

      {layout.error ? <ErrorState message={layout.error} onRetry={layout.reload} /> : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card className="p-0">
          {layout.loading && !layout.data ? (
            <Skeleton className="h-[520px]" />
          ) : layout.data && layout.data.racks.length > 0 ? (
            <div className="h-[520px] overflow-hidden rounded-xl">
              <WarehouseScene racks={layout.data.racks} selected={selection} onSelect={setSelection} />
            </div>
          ) : layout.data ? (
            <div className="flex h-[520px] items-center justify-center">
              <EmptyState
                title="Insufficient inventory data"
                description="This store has no inventory rows, so no rack risk can be derived. Nothing is fabricated to fill the scene."
              />
            </div>
          ) : null}
        </Card>

        <Card>
          <SectionTitle
            title="Location detail"
            subtitle={selection ? selection.locationCode : "Select a shelf"}
            action={
              selectedShelf ? <Badge className={RISK_STYLES[selectedShelf.risk_band]}>{selectedShelf.risk_band.replace("_", " ")}</Badge> : null
            }
          />

          {!selection ? (
            <p className="text-xs text-slate-500">
              Click any shelf in the model to see the SKUs actually stored there, their ageing and their dead-stock risk.
            </p>
          ) : !selectedShelf || selectedShelf.unit_count === 0 ? (
            <div className="rounded-lg border border-dashed border-base-600 p-4 text-center">
              <p className="text-sm text-slate-300">Insufficient inventory data</p>
              <p className="mt-1 text-[11px] text-slate-500">
                No inventory rows exist for {selection.locationCode}.
              </p>
            </div>
          ) : (
            <>
              <dl className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-md border border-base-600/60 bg-base-900/40 p-2">
                  <dt className="text-slate-500">Units</dt>
                  <dd className="mt-0.5 font-mono text-slate-100">{number(selectedShelf.total_units)}</dd>
                </div>
                <div className="rounded-md border border-base-600/60 bg-base-900/40 p-2">
                  <dt className="text-slate-500">Value</dt>
                  <dd className="mt-0.5 font-mono text-slate-100">{money(selectedShelf.total_value)}</dd>
                </div>
                <div className="rounded-md border border-base-600/60 bg-base-900/40 p-2">
                  <dt className="text-slate-500">Risk score</dt>
                  <dd className="mt-0.5 font-mono text-slate-100">{percent(selectedShelf.risk_score, 0)}</dd>
                </div>
                <div className="rounded-md border border-base-600/60 bg-base-900/40 p-2">
                  <dt className="text-slate-500">Candidates</dt>
                  <dd className="mt-0.5 font-mono text-signal-critical">{selectedShelf.recovery_candidates}</dd>
                </div>
              </dl>

              <div className="mt-4 space-y-2">
                {selectedShelf.items.map((item) => (
                  <div key={item.sku} className="rounded-lg border border-base-600/60 bg-base-900/40 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-mono text-[11px] text-slate-300">{item.sku}</p>
                        <p className="truncate text-xs text-slate-400" title={item.name}>
                          {item.name}
                        </p>
                      </div>
                      <Badge className={RISK_STYLES[item.risk_band]}>{item.risk_band.replace("_", " ")}</Badge>
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-2 text-[11px] text-slate-400">
                      <span>
                        Qty <span className="font-mono text-slate-200">{number(item.quantity)}</span>
                      </span>
                      <span>
                        Age <span className="font-mono text-slate-200">{number(item.age_days)}d</span>
                      </span>
                      <span>
                        Locked <span className="font-mono text-slate-200">{money(item.capital_locked)}</span>
                      </span>
                    </div>
                    {item.is_recovery_candidate ? (
                      <div className="mt-2 flex items-center gap-2">
                        <Badge className="border-signal-critical/40 bg-signal-critical/10 text-signal-critical">
                          <Boxes className="h-3 w-3" aria-hidden /> Dead stock
                        </Badge>
                        <Link
                          href={`/recovery-studio?product_id=${item.product_id}&store=${layout.data?.store?.code ?? store}`}
                          className="focus-ring ml-auto inline-flex items-center gap-1 rounded-md border border-accent-cyan/40 px-2 py-0.5 text-[11px] text-accent-cyan hover:bg-accent-cyan/10"
                        >
                          <Sparkles className="h-3 w-3" aria-hidden /> Recover
                        </Link>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
