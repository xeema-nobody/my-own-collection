import type { WishEntry } from "./api";

/** "raw" or "PSA 9": the version of the card the entry wants. */
export const wantLabel = (w: Pick<WishEntry, "grading">) => (w.grading ? `${w.grading.company} ${w.grading.grade}` : "raw");

/** Euros typed by the user -> integer cents; null when empty, undefined when not a positive number. */
export function eurosToCents(text: string): number | null | undefined {
  const t = text.trim().replace(",", ".");
  if (!t) return null;
  const n = Number(t);
  return n > 0 ? Math.round(n * 100) : undefined;
}

export type WishFilter = "all" | "hit" | "noprice";

export function filterWishes(items: WishEntry[], f: WishFilter): WishEntry[] {
  if (f === "hit") return items.filter((w) => w.hit);
  if (f === "noprice") return items.filter((w) => w.value == null);
  return items;
}

/** Case-insensitive match on card name, number, set and note. */
export function searchWishes(items: WishEntry[], q: string): WishEntry[] {
  const t = q.trim().toLowerCase();
  if (!t) return items;
  return items.filter((w) => [w.card?.name, w.card?.number, w.card?.set?.name, w.note, w.variant].some((x) => x?.toLowerCase().includes(t)));
}

export const WISH_SORTS = [
  { value: "added", label: "Date added" }, { value: "value", label: "Price now" }, { value: "gap", label: "Gap to target" },
  { value: "target", label: "Target" }, { value: "name", label: "Name" },
];
const WISH_DESC = ["added", "value"];
export const wishDir = (sort: string, order: string): "asc" | "desc" => (order === "asc" || order === "desc" ? order : WISH_DESC.includes(sort) ? "desc" : "asc");

/** Sort by key; entries with no value for it always go last. "added" keeps the API order (newest first) unless reversed. */
export function sortWishes(items: WishEntry[], sort: string, order: string): WishEntry[] {
  const dir = wishDir(sort, order);
  const key: Record<string, (w: WishEntry) => number | string | null> = {
    added: (w) => w.created_at, value: (w) => w.value, gap: (w) => w.gap, target: (w) => w.target_price,
    name: (w) => w.card?.name?.toLowerCase() ?? null,
  };
  const k = key[sort] ?? key.added;
  const cmp = (a: number | string, b: number | string) => (a < b ? -1 : a > b ? 1 : 0) * (dir === "desc" ? -1 : 1);
  const have = items.filter((w) => k(w) != null);
  return [...have].sort((a, b) => cmp(k(a)!, k(b)!)).concat(items.filter((w) => k(w) == null));
}
