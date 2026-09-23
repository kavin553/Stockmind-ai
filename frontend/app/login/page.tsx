"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Boxes, Loader2, TriangleAlert } from "lucide-react";
import { api, getToken, setSession } from "@/lib/api";

const DEMO_ACCOUNTS = [
  { email: "manager@stockmind.demo", label: "Store Manager" },
  { email: "inventory@stockmind.demo", label: "Inventory Staff" },
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("manager@stockmind.demo");
  const [password, setPassword] = useState("demo1234");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (getToken()) router.replace("/dashboard");
  }, [router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { token, user } = await api.login(email.trim(), password);
      setSession(token, user);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 flex items-center gap-3">
          <div className="rounded-xl border border-accent-cyan/30 bg-accent-cyan/10 p-2 shadow-glow">
            <Boxes className="h-7 w-7 text-accent-cyan" aria-hidden />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-slate-50">StockMind AI</h1>
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Dead Stock Recovery Platform</p>
          </div>
        </div>

        <form onSubmit={submit} className="panel space-y-4 p-6">
          <p className="text-sm text-slate-400">Sign in to the recovery console.</p>

          <label className="block">
            <span className="label-caps">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="focus-ring mt-1 w-full rounded-lg border border-base-600 bg-base-900/70 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600"
              placeholder="you@company.com"
              autoComplete="username"
            />
          </label>

          <label className="block">
            <span className="label-caps">Password</span>
            <input
              type="password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="focus-ring mt-1 w-full rounded-lg border border-base-600 bg-base-900/70 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600"
              placeholder="••••••••"
              autoComplete="current-password"
            />
          </label>

          {error ? (
            <div className="flex items-start gap-2 rounded-lg border border-signal-critical/40 bg-signal-critical/10 p-3 text-xs text-signal-critical">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{error}</span>
            </div>
          ) : null}

          <button
            type="submit"
            disabled={loading}
            className="focus-ring flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-accent-cyan to-accent-blue px-4 py-2.5 text-sm font-semibold text-base-900 transition-opacity hover:opacity-90 disabled:opacity-60"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}
            {loading ? "Signing in…" : "Sign in"}
          </button>

          <div className="border-t border-base-600/60 pt-4">
            <p className="label-caps">Demo accounts (password: demo1234)</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {DEMO_ACCOUNTS.map((account) => (
                <button
                  key={account.email}
                  type="button"
                  onClick={() => {
                    setEmail(account.email);
                    setPassword("demo1234");
                  }}
                  className="focus-ring rounded-md border border-base-600 px-2.5 py-1 text-[11px] text-slate-400 hover:border-accent-cyan/40 hover:text-accent-cyan"
                >
                  {account.label}
                </button>
              ))}
            </div>
          </div>
        </form>

        <p className="mt-6 text-center text-xs text-slate-600">
          Local demo authentication. Inventory, sales and buyer data are seeded; every KPI is computed from it.
        </p>
      </div>
    </div>
  );
}
