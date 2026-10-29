import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import { usePriceGrade } from "../lib/priceGrade";
import PriceMatrix from "./PriceMatrix";
import PriceChart from "./PriceChart";
import SalesList from "./SalesList";

const cell = (price: number, kind = "market") => ({ kind, price, currency: "EUR", observed_on: "2026-10-28", variant: null, url: null, fetched_at: null, as_of: null, sample_size: null });
const matrix = {
  graders: ["PSA", "CGC"], sources: ["pricecharting", "altxyz"],
  grades: ["raw", "G9", "PSA10", "PSA9", "PSA8", "CGC10"],
  cells: { raw: { pricecharting: cell(1000) }, G9: { pricecharting: cell(2000) }, PSA10: { pricecharting: cell(9000, "sold"), altxyz: cell(9500, "sold") },
    PSA9: { pricecharting: cell(5000) }, PSA8: {}, CGC10: { pricecharting: cell(8000) } },
};
const routes = { "/api/cards/c1/price-matrix": matrix, "/api/admin/price-sources": [{ id: "pricecharting", enabled: true }, { id: "altxyz", enabled: true }],
  "/api/cards/c1/prices": [{ source: "pricecharting", kind: "market", observed_on: "2026-10-28", market_base: 2000, base_currency: "EUR", variant: null }] };

function Matrix() { const pg = usePriceGrade("c1"); return <PriceMatrix pg={pg} />; }
function Chart() { const pg = usePriceGrade("c1"); return <PriceChart cardId="c1" pg={pg} />; }

describe("PriceMatrix", () => {
  it("shows only the chosen company, hides empty grades, toggles them", async () => {
    mockApi(routes);
    renderPage(<Matrix />);
    expect(await screen.findByText("Raw", { selector: "td" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "PSA" }));
    expect(await screen.findByText("PSA 10")).toBeInTheDocument();
    expect(screen.queryByText("PSA 8")).not.toBeInTheDocument();   // empty row hidden
    expect(screen.queryByText("CGC 10")).not.toBeInTheDocument();  // other company
    await userEvent.click(screen.getByRole("checkbox", { name: "Show empty grades" }));
    expect(screen.getByText("PSA 8")).toBeInTheDocument();
  });
  it("Any tab explains the missing grade 10", async () => {
    mockApi(routes);
    renderPage(<Matrix />);
    await userEvent.click(await screen.findByRole("radio", { name: "Any" }));
    expect(screen.getByText(/no grade 10/)).toBeInTheDocument();
  });
  it("selector state is shared with the chart through the URL", async () => {
    mockApi(routes);
    renderPage(<><Matrix /><Chart /></>, "/?grade=PSA10");
    expect(await screen.findAllByRole("radio", { name: "PSA", checked: true })).toHaveLength(2);
  });
});

describe("PriceChart", () => {
  it("single point shows the build-up hint", async () => {
    mockApi(routes);
    renderPage(<Chart />);
    expect(await screen.findByText(/One point so far/)).toBeInTheDocument();
  });
  it("empty history explains itself", async () => {
    mockApi({ ...routes, "/api/cards/c1/prices": [] });
    renderPage(<Chart />);
    expect(await screen.findByText(/No price history for Raw yet/)).toBeInTheDocument();
  });
});

describe("SalesList", () => {
  const sales = Array.from({ length: 25 }, (_, i) => ({ id: `s${i}`, sold_at: "2026-10-01", source: i < 20 ? "pricecharting" : "altxyz", grade_key: i < 20 ? "PSA10" : "CGC9", price: 1000, currency: "EUR", title: `Sale ${i}`, url: i === 0 ? "https://example.com/x" : null }));
  const stats = [{ grade_key: "PSA10", source: "pricecharting", count: 20, min: 900, avg: 1000, max: 1100, currency: "EUR" }];
  it("stats table, paging and filters", async () => {
    renderPage(<SalesList sales={sales} stats={stats} />);
    expect(screen.getAllByText("PSA 10", { selector: "td" }).length).toBeGreaterThan(1);
    expect(screen.getByText("25 of 25")).toBeInTheDocument();
    expect(screen.queryByText("Sale 24")).not.toBeInTheDocument();       // only first 20 shown
    await userEvent.click(screen.getByRole("button", { name: "Show 5 more" }));
    expect(screen.getByText("Sale 24")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open listing" })).toHaveAttribute("href", "https://example.com/x");
  });
});
