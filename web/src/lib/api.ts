// Single API client: all backend calls go through here.
// "" (set at build time for the phone page) = same origin; unset = the local API
const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8100";

/** Scraped/upstream urls end up in href: only http(s) may become a link (blocks javascript:). */
export const safeUrl = (u: string | null | undefined): string | undefined =>
  u && /^https?:\/\//i.test(u) ? u : undefined;

export type PackStrategy = "market" | "under" | "floor";
export type PackItem = { item_id: string; card_id: string; title: string; description: string; price: number | null; currency: string;
  quantity: number; photos: string[]; warnings: string[]; sale?: StackSale | null;
  slab: boolean; vinted_condition: VintedCondition; vinted_parcel: VintedParcel; vinted_url: string | null };
export type VintedCondition = "New with tags" | "New without tags" | "Very good" | "Good" | "Satisfactory";
export type VintedParcel = "small" | "medium" | "large";
export type PublishState = "confirmed" | "publishing" | "published" | "failed" | "cancelled";
export type PublishRow = { item_id: string; title: string; description: string; price: number; currency: string; condition: VintedCondition; parcel: VintedParcel };
export type PublishEntry = { id: string; item_id: string; state: PublishState; mode: "create" | "update"; url: string | null; error: string | null;
  photos: number; payload: PublishRow; updated_at: string };
export type PublishConfirmResult = { queued: number; failed: number; results: { item_id: string; ok: boolean; id?: string; error?: string }[] };
export type ListingPack = { platform: string; strategy: PackStrategy; pct: number; items: PackItem[]; missing: string[] };

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

export type ExitReason = "sold" | "gifted" | "removed";
export type Platform = "vinted" | "cardmarket" | "ebay" | "marktplaats" | "other";
export type SaleStatus = "none" | "ready" | "listed" | "reserved" | "withdrawn";
export type Listing = { platform: Platform; asking_price: number; currency: string; listed_at?: string | null; url?: string | null; notes?: string | null; shipping?: number | null; asking_base?: number | null };
export type StackSale = { status: SaleStatus; listings: Listing[] };
export type RemoveExtra = { reason?: ExitReason; price?: number | null; currency?: string; note?: string | null;
  platform?: Platform | null; fees?: number | null; shipping_paid?: number | null };
export type SalesReport = { by_status: Record<string, { stacks: number; cards: number }>; listed_value: number;
  platforms: Record<string, { stacks: number; cards: number; value: number }>;
  sold: { sales: number; cards: number; revenue: number; fees: number; shipping: number; realised: number | null; realised_known: number; avg_days_to_sell: number | null } };
export type BulkRemoveResult = { removed: number; copies?: number; failed: number; results: { id: string; ok: boolean; removed?: number; error?: string }[] };
export type CollectionExit = { id: string; card_id: string; quantity: number; reason: ExitReason; price: number | null; currency: string; date: string; note: string | null; created_at: string; platform?: Platform | null; fees?: number | null; shipping_paid?: number | null; realised?: number | null; listed_days?: number | null; delist?: string[]; card: { name: string; number: string; set: string; image: string | null } | null };

/** One card version offered by the phone scanner (`/api/scan/*`). Money = cents in the base currency. */
export type ScanCard = {
  id: string; name: string; number: string | null; printed_total: number | null; set: { id: string; name: string };
  year: number | null; rarity: string | null; image: string | null; variants: string[]; price: number | null; language: string;
  edition_note: string | null; owned_qty: number;
  signals?: string[]; match_label?: string | null;
  owned: { condition: string | null; language: string; variant: string | null; grading: unknown; quantity: number }[];
};
export type ScanRead = { number: string | null; printed_total: number | null; set_code: string | null; hp: number | null };
/** What the slab label read as. `grader_seen` false = the grader was guessed from the label layout (confirm it). `cert_sure` false = the cert has a length the grader does not print, so it was not looked up. */
export type ScanSlab = { grader: string | null; grade: number | null; cert: string | null; tier?: string | null; grader_seen?: boolean; cert_sure?: boolean; cert_alt?: string[] };
/** A grader's cert page as read by the server (`status` found | not_found | blocked | unavailable | link_only | invalid). */
export type CertInfo = { grader: string; cert: string; status: string; url: string | null; name?: string | null; number?: string | null;
  printed_total?: number | null; set_name?: string | null; year?: number | null; language?: string | null; variant?: string | null;
  grade?: number | null; tier?: string | null; detail?: string | null };
export type JaSuggest = { id: string; name: string; total: number | null; printed_total: number | null; imported: number; reason: string };
export type JaImportStatus = { state: "idle" | "running" | "done" | "partial" | "error"; set: string | null; done: number; expected: number | null; failed: string[] };
export type ScanCert = { cert: CertInfo; cards: ScanCard[]; how_exact: "exact" | "likely" | "possible" | "none"; needs_confirm: boolean; cached: boolean; report_url: string | null; warnings?: { code: string; text: string }[] };
export type ScanIdentify = { text: string; confidence: "high" | "medium" | "low" | "none"; names: string[]; total: number; cards: ScanCard[]; read?: ScanRead | null; exact?: boolean; slab?: ScanSlab | null; detected?: boolean; cert?: ScanCert | null };
export type ScanSearch = { total: number; page: number; cards: ScanCard[] };
export type PhotoKind = "front" | "back" | "corner" | "surface" | "slab_front" | "slab_back" | "other";
export type Photo = { id: string; stack_id: string; kind: PhotoKind; cover: boolean; order: number; w: number; h: number; bytes: number; created_at: string };
export const photoUrl = (id: string, size: "full" | "thumb" = "full") => `${BASE}/api/photos/${id}?size=${size}`;
export type ScanAdded = { label: string; stack: { id: string; quantity: number; type_conflict?: boolean; duplicate?: boolean }; event: ScanEvent };
export type ScanEvent = { id: string; at: string; kind?: "add" | "undo"; card_id: string; label: string; quantity_added: number; quantity_after: number; type_conflict: boolean;
  condition?: string | null; language?: string | null; grading?: unknown; session_id?: string | null; undoes?: string | null };
export type ScanSession = { id: string; created_at: string; mode: "raw" | "slab" };
export type ScanUndone = { label: string; quantity: number; deleted: boolean; event_id: string };
export type ScanStatus = { enabled: boolean; url: string | null; login: string | null };

export type FetchLog = { status: string; detail: string | null; url: string | null; fetched_at: string | null };
export type FetcherStatus = { up: boolean; browser?: string; sites?: Record<string, string>; last_error?: string | null; detail?: string };

export type AlertRule = {
  id: string; description: string; scope: "stack" | "card" | "total" | "wish"; op: "above" | "below" | "up_pct" | "down_pct";
  threshold: number; days: number | null; kind: "any" | "sold" | "market"; include_estimated: boolean;
  enabled: boolean; triggered: boolean; last_value: number | null; last_pct: number | null; last_eval: string | null;
};
export type AlertEvent = {
  id: string; type: "alert" | "system"; rule: string; card_id: string | null; name: string | null;
  value?: number; prev?: number | null; pct?: number | null; price_kind?: string | null; thin?: boolean;
  estimated?: boolean; source?: string | null; fired_at: string; read: boolean;
};
export type AlertIn = {
  scope: string; item_id?: string; card_id?: string; wish_id?: string; op: string; threshold: number; days?: number;
  kind: string; include_estimated: boolean;
};

export type WishEntry = {
  id: string; card_id: string; variant: string | null; grading: { company: string; grade: number; cert_number?: string | null; report_url?: string | null } | null;
  target_price: number | null; note: string | null; alert: boolean; created_at: string;
  card: { _id: string; name: string; number: string; rarity?: string; set?: { name: string }; images?: { small?: string } } | null;
  value: number | null; estimated: boolean; price_kind: string | null; source: string | null; thin: boolean; stale: boolean;
  needs_price: boolean; gap: number | null; hit: boolean;
};
export type WishIn = {
  card_id: string; variant?: string | null; grading?: { company: string; grade: number } | null;
  target_price?: number | null; note?: string | null; alert?: boolean;
};

export type AcqType = "purchased" | "pulled" | "traded" | "gift" | "other";
/** Cost + how a stack was acquired. `price` = cents PER COPY (null = unknown, 0 = free). */
export type Acquired = { type?: AcqType | null; price?: number | null; currency?: string; date?: string | null; source?: string | null };
/** Partial edit: only keys present are applied, null clears. */
export type AcquiredPatch = Acquired;
export type AcqEdit = { id: string; action: "edit" | "bulk" | "merge" | "import" | "restore"; at: string; before: Acquired | null; after: Acquired | null };

/** Totals of the whole filtered set (not just the page). Money = cents; pl is null when no stack has cost + value. */
export type CollectionTotals = { stacks: number; cards: number; value: number; cost: number; pl: number | null; pl_ex_pulled: number | null;
  cost_basis_cost: number; cost_basis_cost_ex_pulled: number; cost_missing: number; needs_price: number; unpriced: number; listed_stacks?: number; listed_value?: number; ready_stacks?: number };
export type CollectionPage = { total: number; items: any[]; totals?: CollectionTotals };
export type FacetValue = { value: string; count: number; label?: string };
export type CollectionFacets = { sets: FacetValue[]; rarities: FacetValue[]; types: FacetValue[]; languages: FacetValue[];
  conditions: FacetValue[]; graders: FacetValue[]; grades: FacetValue[]; platforms: FacetValue[]; sale_statuses: FacetValue[] };
export type PresetScope = "collection" | "wishlist";
export type Preset = { id: string; name: string; scope: PresetScope; query: Record<string, string> };

export const api = {
  cards: (p: Record<string, unknown>) => req<any>("/api/cards" + qs(p)),
  card: (id: string) => req<any>(`/api/cards/${encodeURIComponent(id)}`),
  priceHistory: (id: string, p: { source?: string[]; kind?: string; grade_key?: string; days?: number } = {}) =>
    req<any[]>(`/api/cards/${encodeURIComponent(id)}/prices` + qs(p)),
  priceMatrix: (id: string) => req<any>(`/api/cards/${encodeURIComponent(id)}/price-matrix`),
  priceSources: () => req<any[]>("/api/admin/price-sources"),
  addSale: (id: string, b: unknown) => req<any>(`/api/cards/${encodeURIComponent(id)}/sales`, post(b)),
  cardCompare: (id: string, p: { company?: string; grade?: number; variant?: string } = {}) =>
    req<any>(`/api/cards/${encodeURIComponent(id)}/compare` + qs(p)),
  cardMatches: (id: string) => req<any>(`/api/cards/${encodeURIComponent(id)}/match`),
  confirmMatch: (id: string, source: string, url: string) =>
    req<any>(`/api/cards/${encodeURIComponent(id)}/match/${source}`, post({ url })),
  clearMatch: (id: string, source: string) =>
    req<void>(`/api/cards/${encodeURIComponent(id)}/match/${source}`, { method: "DELETE" }),
  fetchStatus: (id: string) => req<Record<string, FetchLog | null>>(`/api/cards/${encodeURIComponent(id)}/fetch-status`),
  fetcherStatus: () => req<FetcherStatus>("/api/admin/fetcher-status"),
  sets: (withStats = false, language?: string) => req<any[]>("/api/sets" + qs({ with_stats: withStats || undefined, language })),
  filters: () => req<any>("/api/filters"),
  ownedItems: (cardId: string) => req<any>("/api/collection" + qs({ card_id: cardId })),
  collection: (p: Record<string, unknown>) => req<CollectionPage>("/api/collection" + qs(p)),
  collectionFacets: () => req<CollectionFacets>("/api/collection/facets"),
  presets: (scope: PresetScope) => req<Preset[]>("/api/collection/presets" + qs({ scope })),
  savePreset: (b: { name: string; scope: PresetScope; query: Record<string, string> }) => req<Preset>("/api/collection/presets", post(b)),
  deletePreset: (id: string) => req<void>(`/api/collection/presets/${id}`, { method: "DELETE" }),
  exportCollectionUrl: (format: "json" | "csv") => `${BASE}/api/collection/export?format=${format}`,
  importCollection: async (file: File, format: "json" | "csv", mode: "set" | "add") => {
    const r = await fetch(`${BASE}/api/collection/import${qs({ format, mode })}`, { method: "POST", body: file });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new ApiError(typeof body.detail === "string" ? body.detail : r.statusText, r.status);
    return body as { created: number; updated: number; errors: { row: number; error: string }[] };
  },
  patchStack: (id: string, b: { acquired?: AcquiredPatch; notes?: string | null }) =>
    req<any>(`/api/collection/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  bulkAcquired: (ids: string[], acquired: AcquiredPatch) =>
    req<{ updated: number; unchanged: number; missing: string[] }>("/api/collection/bulk-acquired", post({ ids, acquired })),
  stackHistory: (id: string) => req<AcqEdit[]>(`/api/collection/${id}/history`),
  restoreEdit: (id: string, editId: string) => req<any>(`/api/collection/${id}/history/${editId}/restore`, { method: "POST" }),
  collectionSummary: () => req<any>("/api/collection/summary"),
  addToCollection: (b: unknown) => req<any>("/api/collection", post(b)),
  removeFromCollection: (id: string, quantity = 1, extra: RemoveExtra = {}) =>
    req<{ deleted: boolean; quantity: number; removed: number; realised?: number | null; delist?: string[] }>(`/api/collection/${id}/remove`, post({ quantity, ...extra })),
  bulkRemoveStacks: (ids: string[], reason: ExitReason, note?: string | null) =>
    req<BulkRemoveResult>("/api/collection/bulk-remove", post({ ids, reason, note: note || null })),
  setSale: (id: string, b: StackSale) => req<{ id: string; sale: StackSale }>(`/api/collection/${id}/sale`, { method: "PUT", body: JSON.stringify(b) }),
  bulkSale: (ids: string[], status: Exclude<SaleStatus, "listed">) =>
    req<{ updated: number; failed: number; results: { id: string; ok: boolean; dropped_listings?: number; error?: string }[] }>("/api/collection/bulk-sale", post({ ids, status })),
  listingPack: (b: { ids: string[]; platform: "vinted" | "cardmarket"; strategy: PackStrategy; pct: number }) =>
    req<ListingPack>("/api/collection/listing-pack", post(b)),
  listingPackCsvUrl: (ids: string[], strategy: PackStrategy, pct: number) =>
    `${BASE}/api/collection/listing-pack.csv${qs({ ids: ids.join(","), strategy, pct })}`,
  publishConfirm: (items: PublishRow[]) => req<PublishConfirmResult>("/api/publish/confirm", post({ items })),
  publishQueue: (states?: PublishState[]) => req<PublishEntry[]>(`/api/publish/queue${qs({ state: states })}`),
  publishAct: (id: string, act: "cancel" | "retry" | "release") => req<PublishEntry>(`/api/publish/queue/${id}/${act}`, { method: "POST" }),
  photosZipUrl: (id: string) => `${BASE}/api/collection/${id}/photos.zip`,
  salesReport: () => req<SalesReport>("/api/collection/sales/report"),
  collectionExits: () => req<CollectionExit[]>("/api/collection/exits"),
  deleteItem: (id: string) => req<void>(`/api/collection/${id}`, { method: "DELETE" }),
  history: (days: number) => req<any[]>(`/api/dashboard/history?days=${days}`),
  breakdown: (by: string) => req<any[]>(`/api/dashboard/breakdown?by=${by}`),
  movers: (days = 7) => req<any>(`/api/dashboard/movers?days=${days}`),
  jobs: () => req<any[]>("/api/admin/jobs"),
  status: () => req<any>("/api/admin/status"),
  importCatalog: (sets?: string[]) => req<any>("/api/admin/catalog/import" + qs({ sets }), { method: "POST" }),
  jaSets: () => req<{ id: string; name: string; total: number | null; printed_total: number | null; imported: number }[]>("/api/admin/catalog/ja/sets"),
  importJaSets: (sets: string[]) => req<any>("/api/admin/catalog/ja/import" + qs({ sets }), { method: "POST" }),
  catalogImagesStatus: () => req<{ legacy: number; restorable: number; top_sets: { set: string; cards: number }[] }>("/api/admin/catalog/images/status"),
  repointCatalogImages: () => req<any>("/api/admin/catalog/images/repoint", { method: "POST" }),
  restoreCatalogImages: () => req<{ restored: number }>("/api/admin/catalog/images/restore", { method: "POST" }),
  catalogAudit: () => req<any>("/api/admin/catalog/audit"),
  retryIncompleteImports: () => req<{ started: boolean; sets: string[] }>("/api/admin/catalog/import/retry-incomplete", { method: "POST" }),
  refreshCardPrice: (id: string) => req<{ found: boolean; prices: number; tracked: boolean }>(`/api/cards/${encodeURIComponent(id)}/refresh-price`, { method: "POST" }),
  refreshPrices: (scope = "tracked", sets?: string[]) =>
    req<any>("/api/admin/prices/refresh" + qs({ scope, sets }), { method: "POST" }),
  fetchPrices: (b: { cards?: string[]; sets?: string[]; owned?: boolean; missing?: boolean; wishlist?: boolean; sources?: string[]; force?: boolean;
    mode?: FetchMode; stale_days?: number; stack_id?: string; scope?: FetchScope }) =>
    req<{ started: boolean; cards: number }>("/api/admin/prices/fetch", post(b)),
  fetchControl: (action: "pause" | "resume" | "cancel") =>
    req<{ ok: boolean }>("/api/admin/prices/fetch/control", post({ action })),
  fetchRetry: () => req<{ started: boolean; cards: number }>("/api/admin/prices/fetch/retry", { method: "POST" }),
  fetchCardPrices: (id: string, b: { sources?: string[]; force?: boolean } = {}) =>
    req<{ started: boolean; cards: number }>(`/api/cards/${encodeURIComponent(id)}/fetch-prices`, post(b)),
  wishlist: (cardId?: string) => req<WishEntry[]>("/api/wishlist" + qs({ card_id: cardId })),
  wishlistPrices: () => req<WishPrices>("/api/wishlist/prices"),
  addWish: (b: WishIn) => req<WishEntry>("/api/wishlist", post(b)),
  patchWish: (id: string, b: { target_price?: number | null; note?: string | null; alert?: boolean }) =>
    req<WishEntry>(`/api/wishlist/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  bulkRemoveWishes: (ids: string[]) => req<BulkRemoveResult>("/api/wishlist/bulk-remove", post({ ids })),
  removeWish: (id: string) => req<void>(`/api/wishlist/${id}`, { method: "DELETE" }),
  alerts: () => req<AlertRule[]>("/api/alerts"),
  createAlert: (b: AlertIn) => req<AlertRule>("/api/alerts", post(b)),
  patchAlert: (id: string, b: Partial<Pick<AlertRule, "enabled" | "include_estimated" | "kind" | "threshold">>) =>
    req<AlertRule>(`/api/alerts/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  deleteAlert: (id: string) => req<void>(`/api/alerts/${id}`, { method: "DELETE" }),
  alertEvents: (unread = false) => req<AlertEvent[]>("/api/alerts/events" + qs({ unread: unread || undefined })),
  markAlertsRead: (ids?: string[]) => req<{ marked: number }>("/api/alerts/events/read", post({ ids })),
  alertUnread: () => req<{ count: number }>("/api/alerts/unread-count"),
  evaluateAlerts: () => req<{ fired: number }>("/api/alerts/evaluate", { method: "POST" }),
  snapshot: () => req<any>("/api/admin/snapshot", { method: "POST" }),
  scanMe: () => req<{ ok: boolean }>("/api/scan/me"),
  scanIdentify: (photo: Blob, slab = false) =>
    req<ScanIdentify>("/api/scan/identify" + qs({ slab: slab ? 1 : undefined }), { method: "POST", body: photo, headers: { "content-type": photo.type || "image/jpeg" } }),
  scanCert: (grader: string, cert: string, opts: { refresh?: boolean; grade?: number | null; tier?: string | null } = {}) =>
    req<ScanCert>("/api/scan/cert" + qs({ grader, cert, refresh: opts.refresh ? 1 : undefined, grade: opts.grade ?? undefined, tier: opts.tier ?? undefined })),
  scanSearch: (q: string, page = 1) => req<ScanSearch>("/api/scan/search" + qs({ q, page })),
  scanAdd: (b: unknown, sessionId?: string | null) => req<ScanAdded>("/api/scan/add" + qs({ session_id: sessionId }), post(b)),
  jaSuggest: (p: { code?: string | null; total?: number | null; set_name?: string | null; q?: string }) =>
    req<{ sets: JaSuggest[] }>("/api/scan/ja/suggest" + qs({ code: p.code || undefined, total: p.total || undefined, set_name: p.set_name || undefined, q: p.q || undefined })),
  jaImport: (set: string) => req<{ started: boolean; set: string }>("/api/scan/ja/import" + qs({ set }), { method: "POST" }),
  jaImportStatus: () => req<JaImportStatus>("/api/scan/ja/import"),
  scanLookup: (number: string, set?: string) => req<ScanIdentify>("/api/scan/lookup" + qs({ number, set: set || undefined })),
  photos: (stackId: string) => req<Photo[]>(`/api/collection/${stackId}/photos`),
  uploadPhoto: (stackId: string, photo: Blob, kind: PhotoKind = "other") =>
    req<Photo>(`/api/collection/${stackId}/photos` + qs({ kind }), { method: "POST", body: photo, headers: { "content-type": photo.type || "image/jpeg" } }),
  scanPhoto: (stackId: string, photo: Blob, kind: PhotoKind = "other") =>
    req<Photo>("/api/scan/photo" + qs({ stack_id: stackId, kind }), { method: "POST", body: photo, headers: { "content-type": photo.type || "image/jpeg" } }),
  patchPhoto: (id: string, b: { kind?: PhotoKind; cover?: boolean; position?: number }) =>
    req<Photo>(`/api/photos/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  deletePhoto: (id: string) => req<void>(`/api/photos/${id}`, { method: "DELETE" }),
  photoStats: () => req<{ count: number; bytes: number }>("/api/photos/stats"),
  scanUndo: (eventId: string) => req<ScanUndone>("/api/scan/undo", post({ event_id: eventId })),
  scanSession: () => req<{ session: ScanSession | null }>("/api/scan/session"),
  scanStartSession: (mode: "raw" | "slab" = "raw") => req<ScanSession>("/api/scan/sessions", post({ mode })),
  scanCloseSession: (id: string) => req<void>(`/api/scan/sessions/${id}`, { method: "DELETE" }),
  scanStatus: () => req<ScanStatus>("/api/scan/status"),
  scanEvents: (after?: string | null, sessionId?: string | null) => req<{ events: ScanEvent[]; latest: string | null }>("/api/scan/events" + qs({ after, session_id: sessionId })),
};

export const money = (cents: number | null | undefined, cur = "EUR") =>
  cents == null ? "—" : new Intl.NumberFormat(undefined, { style: "currency", currency: cur }).format(cents / 100);

/** Bulk refresh selections: all owned / never fetched / stale > N days / most valuable first / one stack. */
export type FetchMode = "all" | "never" | "stale" | "valuable" | "stack";
/** Which cards a bulk run covers; "both" = collection first, then wishlist-only cards. */
export type FetchScope = "collection" | "wishlist" | "both";
export type WishPrices = { cards: number; fresh: number; stale: number; never: number; fresh_days: number };

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
