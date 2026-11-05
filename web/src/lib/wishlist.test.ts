import { describe, expect, it } from "vitest";
import type { WishEntry } from "./api";
import { eurosToCents, filterWishes, searchWishes, sortWishes, wantLabel } from "./wishlist";

const w = (o: Partial<WishEntry>) => ({ id: "1", hit: false, value: 100, grading: null, ...o }) as WishEntry;

describe("wishlist helpers", () => {
  it("labels the wanted version", () => {
    expect(wantLabel(w({}))).toBe("raw");
    expect(wantLabel(w({ grading: { company: "PSA", grade: 9.5 } }))).toBe("PSA 9.5");
  });
  it("parses euros to cents", () => {
    expect(eurosToCents("12.34")).toBe(1234);
    expect(eurosToCents("12,5")).toBe(1250);
    expect(eurosToCents("  ")).toBeNull();
    expect(eurosToCents("0")).toBeUndefined();
    expect(eurosToCents("abc")).toBeUndefined();
  });
  it("filters hits and unpriced", () => {
    const list = [w({ id: "a", hit: true }), w({ id: "b", value: null }), w({ id: "c" })];
    expect(filterWishes(list, "all")).toHaveLength(3);
    expect(filterWishes(list, "hit").map((x) => x.id)).toEqual(["a"]);
    expect(filterWishes(list, "noprice").map((x) => x.id)).toEqual(["b"]);
  });
  it("searches name, set, number and note", () => {
    const list = [w({ id: "a", card: { name: "Charizard", number: "4", set: { name: "Base" } } as any, note: "holo" }),
      w({ id: "b", card: { name: "Mew", number: "151", set: { name: "Celebrations" } } as any, note: null })];
    expect(searchWishes(list, "CHAR").map((x) => x.id)).toEqual(["a"]);
    expect(searchWishes(list, "celeb").map((x) => x.id)).toEqual(["b"]);
    expect(searchWishes(list, "holo").map((x) => x.id)).toEqual(["a"]);
    expect(searchWishes(list, "151").map((x) => x.id)).toEqual(["b"]);
    expect(searchWishes(list, "  ")).toHaveLength(2);
  });
  it("sorts with missing values last in both directions", () => {
    const list = [w({ id: "a", value: 300, gap: 50 }), w({ id: "b", value: null, gap: null }), w({ id: "c", value: 100, gap: -20 })];
    expect(sortWishes(list, "value", "").map((x) => x.id)).toEqual(["a", "c", "b"]);          // value: high first by default
    expect(sortWishes(list, "value", "asc").map((x) => x.id)).toEqual(["c", "a", "b"]);
    expect(sortWishes(list, "gap", "").map((x) => x.id)).toEqual(["c", "a", "b"]);            // gap: most under target first
  });
});
