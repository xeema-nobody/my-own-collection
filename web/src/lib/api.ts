// Single API client: all backend calls go through here.
const BASE = (import.meta.env.VITE_API_URL as string) || "http://localhost:8100";

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new ApiError(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? r.statusText), r.status);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}
const qs = (p: Record<string, unknown>) => {
  const u = new URLSearchParams();
  Object.entries(p).forEach(([k, v]) => {
    if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
    else if (v !== undefined && v !== "" && v !== null) u.set(k, String(v));
  });
  const s = u.toString();
  return s ? "?" + s : "";
};
const post = (b: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(b) });

export type FetchLog = { status: string; detail: string | null; url: string | null; fetched_at: string | null };
export type FetcherStatus = { up: boolean; browser?: string; sites?: Record<string, string>; last_error?: string | null; detail?: string };

export const api = {
  cards: (p: Record<string, unknown>) => req<any>("/api/cards" + qs(p)),
  card: (id: string) => req<any>(`/api/cards/${encodeURIComponent(id)}`),
  priceHistory: (id: string, p: { source?: string[]; kind?: string; grade_key?: string; days?: number } = {}) =>
    req<any[]>(`/api/cards/${encodeURIComponent(id)}/prices` + qs(p)),
  priceMatrix: (id: string) => req<any>(`/api/cards/${encodeURIComponent(id)}/price-matrix`),
  priceSources: () => req<any[]>("/api/admin/price-sources"),
  addSale: (id: string, b: unknown) => req<any>(`/api/cards/${encodeURIComponent(id)}/sales`, post(b)),
  cardMatches: (id: string) => req<any>(`/api/cards/${encodeURIComponent(id)}/match`),
  confirmMatch: (id: string, source: string, url: string) =>
    req<any>(`/api/cards/${encodeURIComponent(id)}/match/${source}`, post({ url })),
  clearMatch: (id: string, source: string) =>
    req<void>(`/api/cards/${encodeURIComponent(id)}/match/${source}`, { method: "DELETE" }),
  fetchStatus: (id: string) => req<Record<string, FetchLog | null>>(`/api/cards/${encodeURIComponent(id)}/fetch-status`),
  fetcherStatus: () => req<FetcherStatus>("/api/admin/fetcher-status"),
  sets: (withStats = false) => req<any[]>("/api/sets" + qs({ with_stats: withStats || undefined })),
  filters: () => req<any>("/api/filters"),
  collection: (p: Record<string, unknown>) => req<any>("/api/collection" + qs(p)),
  collectionSummary: () => req<any>("/api/collection/summary"),
  addToCollection: (b: unknown) => req<any>("/api/collection", post(b)),
  removeFromCollection: (id: string, quantity = 1) => req<any>(`/api/collection/${id}/remove`, post({ quantity })),
  deleteItem: (id: string) => req<void>(`/api/collection/${id}`, { method: "DELETE" }),
  history: (days: number) => req<any[]>(`/api/dashboard/history?days=${days}`),
  breakdown: (by: string) => req<any[]>(`/api/dashboard/breakdown?by=${by}`),
  movers: (days = 7) => req<any>(`/api/dashboard/movers?days=${days}`),
  jobs: () => req<any[]>("/api/admin/jobs"),
  status: () => req<any>("/api/admin/status"),
  importCatalog: (sets?: string[]) => req<any>("/api/admin/catalog/import" + qs({ sets }), { method: "POST" }),
  retryFailedImports: () => req<{ started: boolean; sets: string[] }>("/api/admin/catalog/import/retry-failed", { method: "POST" }),
  refreshPrices: (scope = "collection", sets?: string[]) =>
    req<any>("/api/admin/prices/refresh" + qs({ scope, sets }), { method: "POST" }),
  fetchPrices: (b: { cards?: string[]; sets?: string[]; owned?: boolean; sources?: string[]; force?: boolean }) =>
    req<{ started: boolean; cards: number }>("/api/admin/prices/fetch", post(b)),
  fetchCardPrices: (id: string, b: { sources?: string[]; force?: boolean } = {}) =>
    req<{ started: boolean; cards: number }>(`/api/cards/${encodeURIComponent(id)}/fetch-prices`, post(b)),
  snapshot: () => req<any>("/api/admin/snapshot", { method: "POST" }),
};

export const money = (cents: number | null | undefined, cur = "EUR") =>
  cents == null ? "—" : new Intl.NumberFormat(undefined, { style: "currency", currency: cur }).format(cents / 100);

export const FETCHER_START_CMD = "cd fetcher && .venv/bin/python -m fetcher";
/** Scraped price sources (fetched on demand through the host fetcher). Mirrors `SCRAPED` in app/providers/price. */
export const SCRAPED_SOURCES = ["pricecharting", "cardmarket_web", "altxyz"] as const;

export const ago = (iso: string | null | undefined) => {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso.endsWith("Z") || /[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z").getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 129600) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
};
