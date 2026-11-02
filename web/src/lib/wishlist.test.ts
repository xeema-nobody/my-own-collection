import { describe, expect, it } from "vitest";
import type { WishEntry } from "./api";
import { eurosToCents, filterWishes, wantLabel } from "./wishlist";

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
});
