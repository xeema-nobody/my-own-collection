// Single API client: all backend calls go through here.
const BASE = (import.meta.env.VITE_API_URL as string) || "http://localhost:8100";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? r.statusText));
  }
  return r.status === 204 ? (undefined as T) : r.json();
}
const qs = (p: Record<string, unknown>) => {
  const u = new URLSearchParams();
  Object.entries(p).forEach(([k, v]) => v !== undefined && v !== "" && v !== null && u.set(k, String(v)));
  const s = u.toString();
  return s ? "?" + s : "";
};
const post = (b: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(b) });

export const api = {
  cards: (p: Record<string, unknown>) => req<any>("/api/cards" + qs(p)),
  card: (id: string) => req<any>(`/api/cards/${encodeURIComponent(id)}`),
  priceHistory: (id: string) => req<any[]>(`/api/cards/${encodeURIComponent(id)}/prices`),
  addSale: (id: string, b: unknown) => req<any>(`/api/cards/${encodeURIComponent(id)}/sales`, post(b)),
  sets: () => req<any[]>("/api/sets"),
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
  importCatalog: (set?: string) => req<any>("/api/admin/catalog/import" + qs({ set }), { method: "POST" }),
  refreshPrices: (scope = "collection") => req<any>("/api/admin/prices/refresh" + qs({ scope }), { method: "POST" }),
  snapshot: () => req<any>("/api/admin/snapshot", { method: "POST" }),
};

export const money = (cents: number | null | undefined, cur = "EUR") =>
  cents == null ? "—" : new Intl.NumberFormat(undefined, { style: "currency", currency: cur }).format(cents / 100);
