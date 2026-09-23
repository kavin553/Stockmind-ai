"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import clsx from "clsx";
import {
  Boxes,
  ClipboardList,
  Cuboid,
  Gauge,
  LayoutDashboard,
  LogOut,
  Network,
  Sparkles,
  Store,
  TriangleAlert,
  Trophy,
  Upload,
} from "lucide-react";
import { clearSession, getStoredUser } from "@/lib/api";
import type { User } from "@/lib/types";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/dead-stock", label: "Dead Stock Center", icon: TriangleAlert },
  { href: "/recovery-studio", label: "Recovery Studio", icon: Sparkles },
  { href: "/warehouse", label: "3D Warehouse", icon: Cuboid },
  { href: "/stores", label: "Store Network", icon: Network },
  { href: "/b2b", label: "B2B Market", icon: Store },
  { href: "/history", label: "Action History", icon: ClipboardList },
  { href: "/import", label: "CSV Import", icon: Upload },
  { href: "/demo", label: "Judge Demo Mode", icon: Trophy },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    const stored = getStoredUser();
    if (!stored) {
      router.replace("/login");
      return;
    }
    setUser(stored);
  }, [router]);

  function signOut() {
    clearSession();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-base-600/60 bg-base-800/60 px-4 py-6 lg:flex">
        <Link href="/dashboard" className="focus-ring flex items-center gap-2 rounded-md px-1 py-1">
          <Boxes className="h-6 w-6 text-accent-cyan" aria-hidden />
          <div>
            <p className="text-sm font-semibold tracking-wide text-slate-100">StockMind AI</p>
            <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500">Dead Stock Recovery</p>
          </div>
        </Link>

        <nav className="mt-8 flex-1 space-y-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                className={clsx(
                  "focus-ring flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  active
                    ? "border border-accent-cyan/30 bg-accent-cyan/10 text-accent-cyan"
                    : "border border-transparent text-slate-400 hover:bg-base-700/60 hover:text-slate-100",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-6 border-t border-base-600/60 pt-4">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Gauge className="h-4 w-4 text-accent-blue" aria-hidden />
            <span className="inline-flex items-center gap-1">
              <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-signal-success" />
              API connected
            </span>
          </div>
          {user ? (
            <div className="mt-3">
              <p className="truncate text-xs font-medium text-slate-200">{user.full_name}</p>
              <p className="truncate text-[11px] text-slate-500">{user.role.replace("_", " ")}</p>
              <button
                type="button"
                onClick={signOut}
                className="focus-ring mt-2 inline-flex items-center gap-1.5 rounded-md border border-base-600 px-2 py-1 text-[11px] text-slate-400 hover:border-signal-critical/50 hover:text-signal-critical"
              >
                <LogOut className="h-3 w-3" aria-hidden /> Sign out
              </button>
            </div>
          ) : null}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-base-600/60 bg-base-800/40 px-5 py-3 lg:hidden">
          <span className="text-sm font-semibold text-slate-100">StockMind AI</span>
          <button type="button" onClick={signOut} className="text-xs text-slate-400">
            Sign out
          </button>
        </header>
        <nav className="flex gap-1 overflow-x-auto border-b border-base-600/60 bg-base-800/40 px-3 py-2 lg:hidden">
          {NAV.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "whitespace-nowrap rounded-md px-3 py-1 text-xs",
                pathname.startsWith(href) ? "bg-accent-cyan/10 text-accent-cyan" : "text-slate-400",
              )}
            >
              {label}
            </Link>
          ))}
        </nav>

        <main className="mx-auto w-full max-w-[1600px] flex-1 px-5 py-6">{children}</main>
      </div>
    </div>
  );
}
