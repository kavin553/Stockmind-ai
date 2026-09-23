"use client";

/**
 * Thin REST client for the StockMind AI backend.
 *
 * The browser never touches the database — everything goes through /api.
 * The demo token is kept in localStorage (hackathon-local auth).
 */

import type {
  AnalyzeResponse,
  BuyerRow,
  DashboardResponse,
  DeadStockRow,
  DemoRunResponse,
  ExecuteResponse,
  HistoryRow,
  Paged,
  ProductDetail,
  StoreRow,
  TimelineEvent,
  TransferOpportunity,
  User,
  WarehouseLayout,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "stockmind.token";
const USER_KEY = "stockmind.user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: User): void {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });

  if (response.status === 401) {
    clearSession();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new ApiError("Your session expired. Please sign in again.", 401);
  }

  const text = await response.text();
  const payload = text ? safeJson(text) : null;

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? typeof (payload as { detail: unknown }).detail === "string"
          ? (payload as { detail: string }).detail
          : JSON.stringify((payload as { detail: unknown }).detail)
        : `Request failed with status ${response.status}`;
    throw new ApiError(detail, response.status);
  }
  return payload as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  });
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export const api = {
  async login(email: string, password: string): Promise<{ token: string; user: User }> {
    return request("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  },
  me: () => request<User>("/api/auth/me"),
  health: () => request<{ status: string; database: string; version: string }>("/api/health"),

  dashboard: () => request<DashboardResponse>("/api/dashboard"),

  deadStock: (params: { store?: string; category?: string; risk?: string; min_age?: number } = {}) =>
    request<Paged<DeadStockRow>>(`/api/dead-stock${query({ page_size: 200, ...params })}`),

  inventory: (params: { q?: string; store?: string; category?: string; sort?: string; page?: number } = {}) =>
    request<Paged<Record<string, unknown>>>(`/api/inventory${query({ page_size: 100, ...params })}`),

  product: (id: string, store?: string) => request<ProductDetail>(`/api/products/${id}${query({ store })}`),

  analyze: (productId: string, storeCode: string) =>
    request<AnalyzeResponse>("/api/recovery/analyze", {
      method: "POST",
      body: JSON.stringify({ product_id: productId, store_code: storeCode }),
    }),

  execute: (planId: string, idempotencyKey?: string) =>
    request<ExecuteResponse>("/api/recovery/execute", {
      method: "POST",
      body: JSON.stringify({ plan_id: planId, idempotency_key: idempotencyKey }),
    }),

  timeline: (planId: string) => request<{ events: TimelineEvent[] }>(`/api/recovery/${planId}/timeline`),

  history: (params: { page?: number } = {}) => request<Paged<HistoryRow>>(`/api/recovery/history${query({ page_size: 100, ...params })}`),

  demoRun: () => request<DemoRunResponse>("/api/recovery/demo-run", { method: "POST", body: JSON.stringify({}) }),

  stores: () => request<{ items: StoreRow[] }>("/api/stores"),
  warehouse: (store?: string) => request<WarehouseLayout>(`/api/warehouse${query({ store })}`),
  transferOpportunities: () => request<{ items: TransferOpportunity[] }>("/api/stores/transfer-opportunities"),
  buyers: () => request<{ items: BuyerRow[] }>("/api/b2b-buyers"),

  async importCsv(kind: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    return request<{ accepted: number; rejected: number; created: number; updated: number; errors: { row: number; reason: string }[] }>(
      "/api/import/csv",
      { method: "POST", body: form },
    );
  },
};
