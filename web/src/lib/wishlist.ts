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
