import { describe, expect, it } from "vitest";
import { COLLECTION_DEFAULTS, activeFilterCount, eurosToCentsParam, toApiQuery } from "./collectionList";

describe("collection list helpers", () => {
  it("converts euros to cents, blank on bad input", () => {
    expect(eurosToCentsParam("1")).toBe("100");
    expect(eurosToCentsParam("1,5")).toBe("150");
    expect(eurosToCentsParam("0")).toBe("0");
    expect(eurosToCentsParam("")).toBe("");
    expect(eurosToCentsParam("abc")).toBe("");
    expect(eurosToCentsParam("-2")).toBe("");
  });
  it("maps the URL state to API params (cents, page_size)", () => {
    const q = toApiQuery({ ...COLLECTION_DEFAULTS, price_max: "2.5", size: "100", set: "base1" });
    expect(q).toMatchObject({ price_max: "250", price_min: "", page_size: "100", set: "base1", sort: "added", page: "1" });
    expect("size" in q).toBe(false);
  });
  it("counts active filters, not sort or paging", () => {
    expect(activeFilterCount(COLLECTION_DEFAULTS)).toBe(0);
    expect(activeFilterCount({ ...COLLECTION_DEFAULTS, sort: "value", page: "4", graded: "true", pl: "negative" })).toBe(2);
  });
});
