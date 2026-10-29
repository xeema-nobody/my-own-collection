export type ActiveFilter = { id: string; label: string; keys: string[] };

export const SORT_OPTIONS = [
  { value: "release", label: "Release (newest)" },
  { value: "number", label: "Set number" },
  { value: "name", label: "Name" },
  { value: "price_desc", label: "Price high→low" },
  { value: "price_asc", label: "Price low→high" },
];

const SIMPLE: [string, string][] = [["type", "Type"], ["rarity", "Rarity"], ["supertype", "Supertype"]];

/** Filters currently applied in the URL, one entry per removable chip. `setName` resolves the set id. */
export function activeFilters(sp: URLSearchParams, setName?: (id: string) => string | undefined): ActiveFilter[] {
  const out: ActiveFilter[] = [];
  const set = sp.get("set");
  if (set) out.push({ id: "set", label: `Set: ${setName?.(set) ?? set}`, keys: ["set"] });
  for (const [k, l] of SIMPLE) if (sp.get(k)) out.push({ id: k, label: `${l}: ${sp.get(k)}`, keys: [k] });
  const lo = sp.get("price_min"), hi = sp.get("price_max");
  if (lo || hi) out.push({ id: "price", label: `Price: ${lo ? "€" + lo : "any"} – ${hi ? "€" + hi : "any"}`, keys: ["price_min", "price_max"] });
  const hp = sp.get("has_price");
  if (hp) out.push({ id: "has_price", label: hp === "true" ? "Has price" : "No price", keys: ["has_price"] });
  if (sp.get("owned") === "true") out.push({ id: "owned", label: "Owned only", keys: ["owned"] });
  return out;
}

/** Same URL params with the given keys removed (and page reset). */
export function withoutKeys(sp: URLSearchParams, keys: string[]): URLSearchParams {
  const n = new URLSearchParams(sp);
  [...keys, "page"].forEach((k) => n.delete(k));
  return n;
}
