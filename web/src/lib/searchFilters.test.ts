import { describe, expect, it } from "vitest";
import { activeFilters, withoutKeys } from "./searchFilters";

const p = (s: string) => new URLSearchParams(s);

describe("activeFilters", () => {
  it("empty url -> none; q, sort and page are not filters", () => {
    expect(activeFilters(p("q=char&sort=name&page=3"))).toEqual([]);
  });
  it("resolves set name, falls back to id", () => {
    expect(activeFilters(p("set=sm11"), () => "Unified Minds")[0].label).toBe("Set: Unified Minds");
    expect(activeFilters(p("set=sm11"))[0].label).toBe("Set: sm11");
  });
  it("min and max price merge into one chip clearing both keys", () => {
    const f = activeFilters(p("price_min=10&price_max=50"));
    expect(f).toHaveLength(1);
    expect(f[0]).toMatchObject({ label: "Price: €10 – €50", keys: ["price_min", "price_max"] });
    expect(activeFilters(p("price_max=5"))[0].label).toBe("Price: any – €5");
  });
  it("has_price and owned", () => {
    expect(activeFilters(p("has_price=false&owned=true")).map((f) => f.label)).toEqual(["No price", "Owned only"]);
  });
});

describe("withoutKeys", () => {
  it("drops keys and page, keeps the rest", () => {
    expect(withoutKeys(p("q=a&set=x&page=4&sort=name"), ["set"]).toString()).toBe("q=a&sort=name");
  });
});
