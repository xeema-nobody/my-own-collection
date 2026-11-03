import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderPage } from "../test/utils";
import { CompareCopies } from "./SourceCompare";

const row = (value: number, rule: string) => ({ value, headline_rule: rule, source: "pricecharting",
  sources: { pricecharting: { value, price_kind: "sold", match: "exact", observed_on: "2026-10-28" } } });

describe("CompareCopies", () => {
  it("renders raw and graded copies in one table with one header", () => {
    renderPage(<CompareCopies copies={[{ label: "Raw copy", row: row(1000, "median") }, { label: "Owned: PSA 10 × 2", row: row(9000, "sold wins") }]} />);
    expect(screen.getAllByRole("table")).toHaveLength(1);
    expect(screen.getAllByRole("columnheader", { name: "Source" })).toHaveLength(1);
    expect(screen.getByText("Raw copy")).toBeInTheDocument();
    expect(screen.getByText("Owned: PSA 10 × 2")).toBeInTheDocument();
    expect(screen.getByText(/sold wins/)).toBeInTheDocument();
  });
  it("says so when no copy has a price", () => {
    renderPage(<CompareCopies copies={[{ row: { sources: {} } }]} />);
    expect(screen.getByText(/No source has a price/)).toBeInTheDocument();
  });
});
