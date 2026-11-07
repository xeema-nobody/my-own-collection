import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import Collection from "./Collection";

const summary = { cards: 3, distinct: 2, value: 9000, cost: 3000, pl: 2000, pl_ex_pulled: 1000, cost_missing: 0, cost_basis_cost: 3000,
  cost_basis_cost_ex_pulled: 3000, unpriced: 0, needs_price: 0, no_data: 0, ref_raw_value: 0, estimated: 0, by_source: {}, value_by_kind: {} };
const row = (id: string, card: string, quantity = 2) => ({ id, card_id: card, quantity, language: "en", condition: "NM", grading: null, variant: null,
  card: { name: `Card ${id}`, number: "1", set: { name: "Base" }, images: {} }, value: 5000, cost: 3000, pl: 2000, price_kind: "market",
  needs_price: false, sources: {}, acquired: null });

const setup = (extra: Record<string, unknown> = {}) => mockApi({
  "/api/collection/summary": summary, "/api/dashboard/history": [], "/api/admin/jobs": [],
  "/api/collection": { items: [row("s1", "pokemon:a-1", 2), row("s2", "pokemon:a-1", 1), row("s3", "pokemon:a-3", 4)], total: 3 }, ...extra });

describe("Collection bulk actions (4b)", () => {
  it("Fetch prices sends only the selected stacks' cards, once each", async () => {
    const bodies: any[] = [];
    setup({ "POST /api/admin/prices/fetch": (init?: RequestInit) => { bodies.push(JSON.parse(String(init?.body))); return { started: true, cards: 1 }; } });
    renderPage(<Collection />);
    await userEvent.click(await screen.findByRole("checkbox", { name: /Select Card s1/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Select Card s2/ }));
    await userEvent.click(screen.getByRole("button", { name: "Fetch prices" }));
    await screen.findByText(/Fetching 1 card/);
    expect(bodies).toEqual([{ cards: ["pokemon:a-1"] }]);
  });
  it("Remove confirms with count and copies, sends one reason, shows partial failures", async () => {
    const bodies: any[] = [];
    setup({ "POST /api/collection/bulk-remove": (init?: RequestInit) => { bodies.push(JSON.parse(String(init?.body)));
      return { removed: 1, copies: 2, failed: 1, results: [{ id: "s1", ok: true, removed: 2 }, { id: "s3", ok: false, error: "item not found" }] }; } });
    renderPage(<Collection />);
    await userEvent.click(await screen.findByRole("checkbox", { name: /Select Card s1/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Select Card s3/ }));
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    const dlg = await screen.findByRole("dialog");
    expect(within(dlg).getByText(/Removes 2 stacks \(6 copies in total\)/)).toBeInTheDocument();
    await userEvent.click(within(dlg).getByRole("radio", { name: "Gifted" }));
    await userEvent.click(within(dlg).getByRole("button", { name: "Remove 2" }));
    expect(await within(dlg).findByText(/Removed 1 \(2 copies\), 1 failed/)).toBeInTheDocument();
    expect(within(dlg).getByText(/item not found/)).toBeInTheDocument();
    expect(bodies).toEqual([{ ids: ["s1", "s3"], reason: "gifted", note: null }]);
  });
});
