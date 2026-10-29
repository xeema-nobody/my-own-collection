import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { mockApi, renderPage } from "../test/utils";
import ValueChart from "./ValueChart";

describe("ValueChart", () => {
  it("empty history says so", async () => {
    mockApi({ "/api/dashboard/history": [] });
    renderPage(<ValueChart />);
    expect(await screen.findByText("No history yet")).toBeInTheDocument();
  });
  it("legacy snapshots without total_value are not plotted", async () => {
    mockApi({ "/api/dashboard/history": [{ date: "2026-10-01", total_value: null }] });
    renderPage(<ValueChart />);
    expect(await screen.findByText("No history yet")).toBeInTheDocument();
  });
  it("a single snapshot shows its value as text", async () => {
    mockApi({ "/api/dashboard/history": [{ date: "2026-10-01", total_value: 40818, total_cost: 15800 }] });
    renderPage(<ValueChart />);
    expect(await screen.findByText(/one snapshot so far/)).toBeInTheDocument();
    expect(screen.getByText(/408\.18/)).toBeInTheDocument();
  });
  it("two snapshots render the chart", async () => {
    mockApi({ "/api/dashboard/history": [{ date: "2026-10-01", total_value: 100 }, { date: "2026-10-02", total_value: 200 }] });
    renderPage(<ValueChart />);
    expect(await screen.findByRole("img", { name: "Collection value over time" })).toBeInTheDocument();
  });
});

describe("ValueChart full", () => {
  const snaps = [
    { date: "2026-10-01", total_value: 100, totals_by_source: { pricecharting: 90 } },
    { date: "2026-10-02", total_value: 200, totals_by_source: { pricecharting: 180 } },
  ];
  it("offers 7d range and a compare-sources toggle", async () => {
    mockApi({ "/api/dashboard/history": snaps });
    renderPage(<ValueChart full />);
    expect(await screen.findByRole("radio", { name: "7d" })).toBeInTheDocument();
    expect(await screen.findByRole("checkbox", { name: "Compare sources" })).not.toBeChecked();
  });
  it("compact mode has neither", async () => {
    mockApi({ "/api/dashboard/history": snaps });
    renderPage(<ValueChart />);
    await screen.findByRole("img", { name: "Collection value over time" });
    expect(screen.queryByRole("radio", { name: "7d" })).toBeNull();
    expect(screen.queryByRole("checkbox", { name: "Compare sources" })).toBeNull();
  });
});
