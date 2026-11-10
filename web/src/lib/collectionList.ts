// Collection list: URL params, mapping to the API, built-in presets. Shared by the page and its tests.
export const COLLECTION_DEFAULTS = {
  q: "", set: "", rarity: "", type: "", language: "", condition: "", graded: "", grader: "", grade: "", acquisition: "",
  price_min: "", price_max: "", pl: "", sale: "", platform: "", has_photos: "", needs_price: "", stale: "", cost_missing: "",
  sort: "added", order: "", page: "1", size: "50",
};
export type CollectionParams = typeof COLLECTION_DEFAULTS;
export const FILTER_KEYS = ["q", "set", "rarity", "type", "language", "condition", "graded", "grader", "grade", "acquisition",
  "price_min", "price_max", "pl", "sale", "platform", "has_photos", "needs_price", "stale", "cost_missing"] as const;
/** What a saved preset covers: the filters plus the sort. */
export const PRESET_KEYS = [...FILTER_KEYS, "sort", "order"] as const;
export const DEFAULT_DESC = ["added", "value", "cost", "pl", "qty", "updated", "listed"];

export const SORT_OPTIONS = [
  { value: "added", label: "Date added" }, { value: "value", label: "Value" }, { value: "cost", label: "Cost" },
  { value: "pl", label: "P/L" }, { value: "name", label: "Name" }, { value: "set", label: "Set" },
  { value: "qty", label: "Quantity" }, { value: "updated", label: "Last price update" },
  { value: "asking", label: "Asking value" }, { value: "listed", label: "Listing date" },
];

/** Euros typed in the URL/UI ("1.5") -> integer cents string; "" when empty or invalid. */
export const eurosToCentsParam = (v: string): string => {
  const n = Number(v.trim().replace(",", "."));
  return v.trim() !== "" && Number.isFinite(n) && n >= 0 ? String(Math.round(n * 100)) : "";
};

export function toApiQuery(f: CollectionParams) {
  const { size, price_min, price_max, ...rest } = f;
  return { ...rest, price_min: eurosToCentsParam(price_min), price_max: eurosToCentsParam(price_max), page_size: size };
}

export const activeFilterCount = (f: CollectionParams) => FILTER_KEYS.filter((k) => f[k] !== "").length;

export type BuiltinPreset = { name: string; query: Record<string, string> };
export const BUILTIN_PRESETS: BuiltinPreset[] = [
  { name: "Graded only", query: { graded: "true" } },
  { name: "Cheap bulk < €1", query: { graded: "false", price_max: "1", sort: "qty" } },
  { name: "Needs price", query: { needs_price: "true" } },
  { name: "Price stale", query: { stale: "true" } },
  { name: "No cost", query: { cost_missing: "true" } },
  { name: "Ready to list", query: { sale: "ready" } },
  { name: "Listed", query: { sale: "listed", sort: "listed" } },
  { name: "Losing money", query: { pl: "negative", sort: "pl", order: "asc" } },
];
