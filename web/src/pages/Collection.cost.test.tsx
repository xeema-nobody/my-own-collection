import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import Collection from "./Collection";

const summary = { cards: 3, distinct: 2, value: 9000, cost: 3000, pl: 2000, pl_ex_pulled: 1000, cost_missing: 1, cost_basis_cost: 3000,
  cost_basis_cost_ex_pulled: 3000, unpriced: 0, needs_price: 0, no_data: 0, ref_raw_value: 0, estimated: 0, by_source: {}, value_by_kind: {} };
const row = (id: string, over: object = {}) => ({ id, card_id: `pokemon:a-${id}`, quantity: 2, language: "en", condition: "NM", grading: null, variant: null,
  card: { name: `Card ${id}`, number: "1", set: { name: "Base" }, images: {} }, value: 5000, cost: 3000, pl: 2000, price_kind: "market",
  needs_price: false, sources: {}, acquired: { type: "pulled", price: 1500, currency: "EUR" }, ...over });

const base = (extra: Record<string, unknown> = {}) => mockApi({
  "/api/collection/summary": summary, "/api/dashboard/history": [],
  "/api/collection": { items: [row("s1"), row("s2", { acquired: null, cost: null, pl: null })], total: 2 }, ...extra });

describe("Collection cost + acquisition", () => {
  it("shows P/L excl. pulled, missing-cost hint and the type badge", async () => {
    base();
    renderPage(<Collection />);
    expect(await screen.findByText("P/L excl. pulled")).toBeInTheDocument();
    expect(screen.getByText("1 stack without cost")).toBeInTheDocument();
    expect(screen.getByText("Pulled")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Show the 1 without cost/ }));
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "No cost" })).toBeChecked());
  });
  it("sends the acquisition filter to the API", async () => {
    const fn = base();
    renderPage(<Collection />, "/?acquisition=unset&cost_missing=true");
    await screen.findByText("Card s1");
    expect(fn.mock.calls.some((c) => String(c[0]).includes("acquisition=unset") && String(c[0]).includes("cost_missing=true"))).toBe(true);
  });
  it("bulk edit posts the selected ids and only the filled fields", async () => {
    const bodies: any[] = [];
    base({ "POST /api/collection/bulk-acquired": (init?: RequestInit) => { bodies.push(JSON.parse(String(init?.body))); return { updated: 2, unchanged: 0, missing: [] }; } });
    renderPage(<Collection />);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Select all on this page" }));
    expect(screen.getByText("2 stacks selected")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Edit cost & type/ }));
    const dlg = await screen.findByRole("dialog");
    await userEvent.type(within(dlg).getByLabelText("Where bought"), "binder");
    await userEvent.click(within(dlg).getByRole("button", { name: "Apply to 2" }));
    await waitFor(() => expect(bodies).toEqual([{ ids: ["s1", "s2"], acquired: { source: "binder" } }]));
    expect(await within(dlg).findByText(/Updated 2, unchanged 0/)).toBeInTheDocument();
  });
  it("details drawer edits a stack and restores from history", async () => {
    const patches: any[] = [], restores: string[] = [];
    mockApi({
      "/api/collection/summary": summary, "/api/dashboard/history": [],
      "/api/collection": { items: [row("s1")], total: 1 },
      "POST /api/collection/s1/history/e1/restore": () => { restores.push("e1"); return {}; },
      "/api/collection/s1/history": [{ id: "e1", action: "edit", at: new Date().toISOString(), before: { type: "purchased", price: 900, currency: "EUR" }, after: { type: "pulled", price: 1500, currency: "EUR" } }],
      "PATCH /api/collection/s1": (init?: RequestInit) => { patches.push(JSON.parse(String(init?.body))); return {}; } });
    renderPage(<Collection />);
    await userEvent.click(await screen.findByRole("button", { name: "Details for Card s1" }));
    const dlg = await screen.findByRole("dialog");
    await userEvent.click(within(dlg).getByRole("button", { name: "Edit cost" }));
    const price = within(dlg).getByLabelText("Price");
    await userEvent.clear(price);
    await userEvent.type(price, "20");
    await userEvent.click(within(dlg).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patches).toEqual([{ acquired: { type: "pulled", price: 2000, currency: "EUR", date: null, source: null } }]));
    await userEvent.click(await within(dlg).findByText(/Edit history/));
    await userEvent.click(within(dlg).getByRole("button", { name: /Restore previous/ }));
    await waitFor(() => expect(restores).toEqual(["e1"]));
  });
});
