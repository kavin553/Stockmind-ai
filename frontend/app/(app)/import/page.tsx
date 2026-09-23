"use client";

import { useRef, useState } from "react";
import { CheckCircle2, FileSpreadsheet, Upload, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Card, ErrorState, SectionTitle } from "@/components/ui";

type ImportResult = {
  accepted: number;
  rejected: number;
  created: number;
  updated: number;
  errors: { row: number; reason: string }[];
};

const KINDS = [
  { value: "sales", label: "Sales history", hint: "sku, store_code, sold_on, quantity, unit_price" },
  { value: "inventory", label: "Inventory snapshot", hint: "sku, store_code, quantity, first_received_at, last_sold_at, location_code" },
  { value: "products", label: "Products (reference only)", hint: "sku, name, category, unit_cost, list_price" },
];

export default function ImportPage() {
  const [kind, setKind] = useState("sales");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function upload(file: File) {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.importCsv(kind, file));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-50">
          <FileSpreadsheet className="h-5 w-5 text-accent-blue" aria-hidden />
          CSV Import
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-500">
          Import sales or inventory. Validation is server-side: negative quantities, zero prices, malformed SKUs,
          unparseable or future dates, unknown stores and duplicate rows are rejected individually, and valid rows are
          still imported.
        </p>
      </header>

      <Card>
        <SectionTitle title="Choose a dataset" />
        <div className="grid gap-3 md:grid-cols-3">
          {KINDS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setKind(option.value)}
              className={`focus-ring rounded-lg border p-3 text-left text-xs transition-colors ${
                kind === option.value
                  ? "border-accent-cyan/50 bg-accent-cyan/5 text-slate-100"
                  : "border-base-600/60 text-slate-400 hover:border-accent-cyan/30"
              }`}
            >
              <p className="font-medium">{option.label}</p>
              <p className="mt-1 font-mono text-[10px] leading-relaxed text-slate-500">{option.hint}</p>
            </button>
          ))}
        </div>

        <div className="mt-5">
          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
            }}
          />
          <button
            type="button"
            disabled={loading}
            onClick={() => inputRef.current?.click()}
            className="focus-ring inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-accent-cyan to-accent-blue px-4 py-2 text-sm font-semibold text-base-900 hover:opacity-90 disabled:opacity-60"
          >
            <Upload className="h-4 w-4" aria-hidden />
            {loading ? "Uploading…" : "Select CSV file"}
          </button>
          <p className="mt-2 text-[11px] text-slate-500">
            Sample files live in <span className="font-mono">data/samples/</span>.
          </p>
        </div>
      </Card>

      {error ? <ErrorState message={error} /> : null}

      {result ? (
        <Card>
          <SectionTitle
            title="Import result"
            action={
              <div className="flex gap-2">
                <Badge className="border-signal-success/40 bg-signal-success/10 text-signal-success">
                  {result.accepted} accepted
                </Badge>
                <Badge
                  className={
                    result.rejected
                      ? "border-signal-critical/40 bg-signal-critical/10 text-signal-critical"
                      : "border-base-600 bg-base-900/40 text-slate-400"
                  }
                >
                  {result.rejected} rejected
                </Badge>
              </div>
            }
          />
          <div className="flex gap-4 text-xs text-slate-400">
            <span className="inline-flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5 text-signal-success" aria-hidden /> created {result.created}
            </span>
            <span>updated {result.updated}</span>
          </div>

          {result.errors.length > 0 ? (
            <div className="mt-4 overflow-hidden rounded-lg border border-base-600/60">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-base-600/70 text-left label-caps">
                    <th className="px-3 py-2">Row</th>
                    <th className="px-3 py-2">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {result.errors.map((rowError, index) => (
                    <tr key={`${rowError.row}-${index}`} className="border-b border-base-700/50">
                      <td className="px-3 py-2 font-mono text-slate-400">{rowError.row}</td>
                      <td className="px-3 py-2 text-signal-critical">
                        <span className="inline-flex items-center gap-1.5">
                          <XCircle className="h-3 w-3" aria-hidden />
                          {rowError.reason}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mt-4 text-xs text-signal-success">Every row passed validation.</p>
          )}
        </Card>
      ) : null}
    </div>
  );
}
