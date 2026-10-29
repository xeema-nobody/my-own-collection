import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { BarList, topN } from "./BarList";

describe("topN", () => {
  it("keeps all rows when within the limit, sorted desc", () => {
    expect(topN([{ name: "a", value: 1 }, { name: "b", value: 3 }], 5).map((r) => r.name)).toEqual(["b", "a"]);
  });
  it("folds the rest into Other", () => {
    const rows = [1, 2, 3, 4, 5].map((v) => ({ name: `r${v}`, value: v }));
    const out = topN(rows, 2);
    expect(out.map((r) => r.name)).toEqual(["r5", "r4", "Other"]);
    expect(out[2].value).toBe(6);
  });
});

describe("BarList", () => {
  it("shows value and share per row", () => {
    render(<BarList label="Value by set" rows={[{ name: "Base Set", value: 7500 }, { name: "Jungle", value: 2500 }]} format={(v) => `€${v / 100}`} />);
    expect(screen.getByRole("list", { name: "Value by set" })).toBeInTheDocument();
    expect(screen.getByText("Base Set")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });
  it("empty total does not divide by zero", () => {
    render(<BarList label="x" rows={[{ name: "a", value: 0 }]} format={String} />);
    expect(screen.getByText("0.0%")).toBeInTheDocument();
  });
});
