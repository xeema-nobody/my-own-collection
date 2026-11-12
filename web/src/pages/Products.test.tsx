import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import Products, { toCents } from "./Products";

const prod = (o: object = {}) => ({ id: "p1", name: "Obsidian Box", type: "booster_box", tcg: "pokemon", set_name: "Obsidian Flames", language: "en",
  quantity: 2, status: "sealed", purchase_price: 12000, purchase_date: null, purchased_from: null, market_value: 14500, market_value_at: "2026-11-12",
  sold_price: null, sold_at: null, note: null, ...o });
const SUM = { value: 29000, cost: 24000, stacks: 1, units: 2, unpriced: 0, cost_missing: 0 };

describe("toCents", () => {
  it("parses euros, rejects junk", () => {
    expect(toCents("12.50")).toBe(1250);
    expect(toCents("12,5")).toBe(1250);
    expect(toCents("")).toBeNull();
    expect(Number.isNaN(toCents("abc"))).toBe(true);
    expect(Number.isNaN(toCents("1.234"))).toBe(true);
  });
});

describe("Products page", () => {
  it("empty state", async () => {
    mockApi({ "/api/products/summary": { ...SUM, value: 0, cost: 0, stacks: 0, units: 0 }, "/api/products": [] });
    renderPage(<Products />);
    expect(await screen.findByText("No products")).toBeInTheDocument();
  });
  it("rows show unit and total value; unknown value is a dash, never 0", async () => {
    mockApi({ "/api/products/summary": SUM, "/api/products": [prod(), prod({ id: "p2", name: "Mystery tin", market_value: null })] });
    renderPage(<Products />);
    expect(await screen.findByText("Obsidian Box")).toBeInTheDocument();
    expect(screen.getByText(/290[.,]00/, { selector: "td" })).toBeInTheDocument();    // 2 x 145.00
    const row = screen.getByText("Mystery tin").closest("tr")!;
    expect(row.querySelectorAll("td")[4].textContent).toBe("—");
    expect(row.querySelectorAll("td")[5].textContent).toBe("—");
  });
  it("add posts cents", async () => {
    let body: any = null;
    mockApi({ "/api/products/summary": SUM, "POST /api/products": (init?: RequestInit) => { body = JSON.parse(String(init?.body)); return prod(); }, "/api/products": [] });
    renderPage(<Products />);
    await userEvent.click(await screen.findByRole("button", { name: /Add product/ }));
    await userEvent.type(screen.getByLabelText("Name"), "ETB");
    await userEvent.type(screen.getByLabelText("Market value per unit (€)"), "55,5");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).toMatchObject({ name: "ETB", market_value: 5550, purchase_price: null, quantity: 1, status: "sealed" }));
  });
  it("rejects a bad price without calling the API", async () => {
    const f = mockApi({ "/api/products/summary": SUM, "/api/products": [] });
    renderPage(<Products />);
    await userEvent.click(await screen.findByRole("button", { name: /Add product/ }));
    await userEvent.type(screen.getByLabelText("Name"), "x");
    await userEvent.type(screen.getByLabelText("Paid per unit (€)"), "abc");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/positive amounts/);
    expect(f.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toBe(false);
  });
  it("delete asks to confirm", async () => {
    const calls: string[] = [];
    mockApi({ "/api/products/summary": SUM, "/api/products": [prod()], "DELETE /api/products/p1": () => { calls.push("del"); return { status: 204 }; } });
    renderPage(<Products />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete Obsidian Box" }));
    expect(calls).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls).toEqual(["del"]));
  });
});
