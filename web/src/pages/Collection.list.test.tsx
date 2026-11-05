import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import Collection from "./Collection";

const summary = { cards: 3, distinct: 2, value: 9000, cost: 3000, pl: 2000, pl_ex_pulled: 1000, cost_missing: 0, cost_basis_cost: 3000,
  cost_basis_cost_ex_pulled: 3000, unpriced: 0, needs_price: 0, no_data: 0, ref_raw_value: 0, estimated: 0, by_source: {}, value_by_kind: {} };
const row = (id: string, over: object = {}) => ({ id, card_id: `pokemon:a-${id}`, quantity: 2, language: "en", condition: "NM", grading: null, variant: null,
  card: { name: `Card ${id}`, number: "1", set: { name: "Base" }, images: {} }, value: 5000, cost: 3000, pl: 2000, price_kind: "market",
  needs_price: false, sources: {}, acquired: null, ...over });
const totals = { stacks: 2, cards: 4, value: 10000, cost: 6000, pl: 4000, pl_ex_pulled: 4000, cost_basis_cost: 6000, cost_basis_cost_ex_pulled: 6000, cost_missing: 0, needs_price: 0, unpriced: 0 };
const facets = { sets: [{ value: "base1", label: "Base Set", count: 2 }], rarities: [{ value: "Rare", count: 1 }], types: [], languages: [], conditions: [], graders: [], grades: [] };

const calls = (fn: ReturnType<typeof mockApi>) => fn.mock.calls.map((c) => String(c[0]));
const setup = (extra: Record<string, unknown> = {}) => mockApi({
  "/api/collection/summary": summary, "/api/dashboard/history": [], "/api/collection/facets": facets, "/api/collection/presets": [],
  "/api/collection": { items: [row("s1"), row("s2")], total: 2, totals }, ...extra });

beforeEach(() => localStorage.clear());

describe("Collection list: filters, totals, views, presets", () => {
  it("sends every URL filter to the API (price in cents) and shows filtered totals", async () => {
    const fn = setup();
    renderPage(<Collection />, "/?set=base1&rarity=Rare&graded=true&grader=PSA&grade=9&pl=negative&price_min=1&price_max=2.5&stale=true&sort=pl&order=asc&page=2&size=25");
    const totalsBar = await screen.findByRole("status", { name: "Filtered totals" });
    expect(within(totalsBar).getByText("2 stacks match")).toBeInTheDocument();
    expect(totalsBar).toHaveTextContent("4 cards");
    const url = new URL(calls(fn).find((u) => u.includes("/api/collection?"))!);
    expect(Object.fromEntries(url.searchParams)).toMatchObject({ set: "base1", rarity: "Rare", graded: "true", grader: "PSA", grade: "9", pl: "negative",
      price_min: "100", price_max: "250", stale: "true", sort: "pl", order: "asc", page: "2", page_size: "25" });
  });
  it("hides the filtered totals when no filter is active", async () => {
    setup();
    renderPage(<Collection />, "/?sort=value");
    await screen.findByText("Card s1");
    expect(screen.queryByRole("status", { name: "Filtered totals" })).not.toBeInTheDocument();
  });
  it("debounces search before it reaches the API", async () => {
    const fn = setup();
    renderPage(<Collection />);
    await screen.findByText("Card s1");
    await userEvent.type(screen.getByLabelText("Search owned"), "pika");
    expect(calls(fn).some((u) => u.includes("q=pik"))).toBe(false);   // not per keystroke
    await waitFor(() => expect(calls(fn).filter((u) => u.includes("q=pika"))).toHaveLength(1), { timeout: 2000 });
  });
  it("grid view shows tiles, opens the drawer, and is remembered", async () => {
    setup();
    const { unmount } = renderPage(<Collection />);
    await screen.findByText("Card s1");
    await userEvent.click(screen.getByRole("radio", { name: /Grid/ }));
    expect(localStorage.getItem("collection.view")).toBe("grid");
    const grid = screen.getByRole("list", { name: "Collection grid" });
    expect(within(grid).getAllByRole("listitem")).toHaveLength(2);
    await userEvent.click(within(grid).getAllByText(/Base #1/)[0]);   // the card name is a link; the tile body opens the drawer
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    unmount();
    renderPage(<Collection />);
    expect(await screen.findByRole("list", { name: "Collection grid" })).toBeInTheDocument();   // choice survives a remount
  });
  it("built-in preset applies its filters and shows as active", async () => {
    const fn = setup();
    renderPage(<Collection />);
    await screen.findByText("Card s1");
    await userEvent.click(screen.getByRole("button", { name: "Graded only" }));
    await waitFor(() => expect(calls(fn).some((u) => u.includes("graded=true"))).toBe(true));
    expect(screen.getByRole("button", { name: "Graded only" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Cheap bulk < €1" }));
    await waitFor(() => expect(calls(fn).some((u) => u.includes("graded=false") && u.includes("price_max=100"))).toBe(true));
  });
  it("saves the current filters as a preset and deletes it", async () => {
    const saved: any[] = [], deleted: string[] = [];
    let list: any[] = [];
    setup({
      "/api/collection/presets": () => list,
      "POST /api/collection/presets": (init?: RequestInit) => { const b = JSON.parse(String(init?.body)); saved.push(b); list = [{ id: "p1", ...b }]; return list[0]; },
      "DELETE /api/collection/presets/p1": () => { deleted.push("p1"); list = []; return { status: 204 }; } });
    renderPage(<Collection />, "/?graded=true&pl=positive&page=3");
    await screen.findByText("Card s1");
    await userEvent.click(screen.getByRole("button", { name: /Save current/ }));
    await userEvent.type(screen.getByLabelText("Preset name"), "My slabs");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toEqual([{ name: "My slabs", scope: "collection", query: { graded: "true", pl: "positive" } }]));   // no page in a preset
    await userEvent.click(await screen.findByRole("button", { name: "Delete preset My slabs" }));
    await waitFor(() => expect(deleted).toEqual(["p1"]));
  });
  it("still renders the list when facets fail", async () => {
    setup({ "/api/collection/facets": { status: 500, body: { detail: "boom" } } });
    renderPage(<Collection />);
    expect(await screen.findByText("Card s1")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Set" })).toBeInTheDocument();
  });
});
