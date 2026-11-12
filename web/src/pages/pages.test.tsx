import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { mockApi, renderPage } from "../test/utils";
import App from "../App";
import Alerts from "./Alerts";
import Collection from "./Collection";
import Dashboard from "./Dashboard";
import Settings from "./Settings";

const down = { status: 503, body: { detail: "db down" } };
const summary = { cards: 0, distinct: 0, value: 0, cost: 0, pl: null, unpriced: 0, needs_price: 0, no_data: 0, ref_raw_value: 0, estimated: 0, by_source: {}, value_by_kind: {} };

describe("Collection", () => {
  it("empty state", async () => {
    mockApi({ "/api/collection/summary": summary, "/api/collection": { items: [], total: 0 } });
    renderPage(<Collection />);
    expect(await screen.findByText(/Nothing here/)).toBeInTheDocument();
  });
  it("API error shows alert", async () => {
    mockApi({ "/api/collection/summary": down, "/api/collection": down, "/api/dashboard/history": [] });
    renderPage(<Collection />);
    expect(await screen.findAllByRole("alert")).toHaveLength(2);
    expect(screen.getAllByText(/db down/).length).toBe(2);
  });
});

describe("Dashboard", () => {
  const ok = {
    "/api/collection/summary": { ...summary, cards: 3, distinct: 2, value: 10000, cost: 8000, pl: 2000, needs_price: 1, value_by_kind: { sold: 5000 }, by_source: {} },
    "/api/dashboard/history": [], "/api/dashboard/breakdown": [{ name: "Base Set", value: 7500 }, { name: "Jungle", value: 2500 }],
    "/api/dashboard/movers": { up: [{ card_id: "c1", name: "Pikachu", grade_key: "raw", kind: "market", source: "x", match: "exact", from: 100, to: 150, pct: 50 }], down: [] },
    "/api/collection": { items: [{ id: "1", card_id: "c9", card: { name: "Charizard" }, condition: "NM", quantity: 1, value: 9000, price_kind: "sold" }], total: 1 },
    "/api/jobs": [],
  };
  it("renders insight sections", async () => {
    mockApi(ok);
    renderPage(<Dashboard />);
    expect(await screen.findByText("Where the value is")).toBeInTheDocument();
    expect(await screen.findByText("Base Set")).toBeInTheDocument();
    expect(await screen.findByText("Charizard")).toBeInTheDocument();
    expect(await screen.findByText("Pikachu")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fetch missing prices" })).toBeEnabled();
  });
  it("shows P/L with and without pulled cards and the missing-cost hint", async () => {
    mockApi({ ...ok, "/api/collection/summary": { ...ok["/api/collection/summary"], pl_ex_pulled: 500, cost_basis_cost: 8000, cost_basis_cost_ex_pulled: 5000, cost_missing: 2 } });
    renderPage(<Dashboard />);
    expect(await screen.findByText("P/L excl. pulled")).toBeInTheDocument();
    expect(screen.getByText("+10.0% vs cost")).toBeInTheDocument();
    expect(screen.getByText("2 stacks without cost")).toBeInTheDocument();
  });
  it("shows opening ROI only when something was opened", async () => {
    const rep = { hit_threshold: 500, products: [{ card_id: "sealed:x", name: "Box", opened: { units: 1, cost: 5000, cost_unknown: 0, pulls_value: 18000, net: 13000 },
      kept: { units: 1, value: 9000, cost: 5000 }, sold: { units: 0, proceeds: 0, realised: 0 } }],
      openings: [{ id: "o1", card_id: "sealed:x", name: "Box", date: "2026-11-12", units: 1, cost: 5000, pulls_value: 18000, net: 13000, roi: 2.6, kept_value: 9000, vs_kept: 9000,
        pulled_copies: 2, priced_copies: 2, unpriced: 0, hits: 2, hit_rate: 1, best_hit: { card_id: "c1", name: "Zard", value: 9000 } }],
      totals: { openings: 1, units: 1, cost: 5000, pulls_value: 18000, net: 13000, roi: 2.6, hit_rate: 1, vs_kept: 9000, excluded_unknown_cost: 0 } };
    mockApi({ ...ok, "/api/openings/report": rep });
    renderPage(<Dashboard />);
    expect(await screen.findByText("Opening ROI")).toBeInTheDocument();
    expect(screen.getByText("Zard · €90.00")).toBeInTheDocument();
  });
  it("hides opening ROI when nothing was opened", async () => {
    mockApi({ ...ok, "/api/openings/report": { openings: [], products: [], hit_threshold: 500, totals: {} } });
    renderPage(<Dashboard />);
    expect(await screen.findByText("Where the value is")).toBeInTheDocument();
    expect(screen.queryByText("Opening ROI")).not.toBeInTheDocument();
  });
  it("empty states", async () => {
    mockApi({ ...ok, "/api/dashboard/breakdown": [], "/api/dashboard/movers": { up: [], down: [] }, "/api/collection": { items: [], total: 0 },
      "/api/collection/summary": summary });
    renderPage(<Dashboard />);
    expect(await screen.findByText("Nothing valued yet")).toBeInTheDocument();
    expect(await screen.findByText("No moves yet")).toBeInTheDocument();
    expect(screen.getByText("No valued stacks")).toBeInTheDocument();
  });
  it("API error shows alerts with Retry", async () => {
    mockApi({ "/api": down });
    renderPage(<Dashboard />);
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Retry" }).length).toBeGreaterThan(0));
  });
});

describe("Alerts", () => {
  it("empty", async () => {
    mockApi({ "/api/alerts/events": [], "/api/alerts": [], "/api/collection": { items: [] } });
    renderPage(<Alerts />);
    expect(await screen.findByText(/No alerts yet/)).toBeInTheDocument();
    expect(screen.getByText("No rules yet")).toBeInTheDocument();
  });
  it("error", async () => {
    mockApi({ "/api/alerts/events": down, "/api/alerts": down, "/api/collection": { items: [] } });
    renderPage(<Alerts />);
    expect(await screen.findByText(/Inbox: db down/)).toBeInTheDocument();
    expect(screen.getByText(/Rules: db down/)).toBeInTheDocument();
  });
  it("lists rules", async () => {
    mockApi({
      "/api/alerts/events": [], "/api/collection": { items: [] },
      "/api/alerts": [{ id: "1", description: "Charizard above 100", enabled: true, triggered: false, include_estimated: false, last_value: 9000, last_pct: null }],
    });
    renderPage(<Alerts />);
    expect(await screen.findByText("Charizard above 100")).toBeInTheDocument();
    expect(screen.getByText("armed")).toBeInTheDocument();
  });
  it("Check now shows 'N new' only when something fired", async () => {
    mockApi({ "/api/alerts/events": [], "/api/alerts": [], "/api/collection": { items: [] }, "POST /api/alerts/evaluate": { fired: 0 } });
    renderPage(<Alerts />);
    await userEvent.click(await screen.findByRole("button", { name: "Check now" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Check now" })).toBeEnabled());
    expect(screen.queryByText(/new$/)).not.toBeInTheDocument();
  });
});

describe("Alerts rule form", () => {
  const base = { "/api/alerts/events": [], "/api/alerts": [] };
  const stack = { id: "s1", card_id: "c1", card: { name: "Squirtle", number: "7" }, condition: "NM", quantity: 1 };
  const posted = (fn: ReturnType<typeof mockApi>) => {
    const c = fn.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST");
    return c ? JSON.parse(String((c[1] as RequestInit).body)) : undefined;
  };
  it("total scope, above: posts cents and shows the sentence", async () => {
    const fn = mockApi({ ...base, "/api/collection": { items: [], total: 0 }, "POST /api/alerts": { id: "n" } });
    renderPage(<Alerts />);
    await userEvent.type(await screen.findByLabelText("Amount"), "100");
    expect(screen.getByText(/alerted when your collection total goes above EUR 100.00/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Add rule/ }));
    await waitFor(() => expect(posted(fn)).toMatchObject({ scope: "total", op: "above", threshold: 10000, kind: "any" }));
  });
  it("percent op reveals days and posts a percentage", async () => {
    const fn = mockApi({ ...base, "/api/collection": { items: [], total: 0 }, "POST /api/alerts": { id: "n" } });
    renderPage(<Alerts />);
    await userEvent.click(await screen.findByRole("combobox", { name: "Condition" }));
    await userEvent.click(await screen.findByRole("option", { name: "rises by" }));
    await userEvent.type(screen.getByLabelText("Amount"), "10");
    await userEvent.click(screen.getByRole("radio", { name: "sold only" }));
    await userEvent.click(screen.getByRole("button", { name: /Add rule/ }));
    await waitFor(() => expect(posted(fn)).toMatchObject({ op: "up_pct", threshold: 10, days: 7, kind: "sold" }));
  });
  it("wishlist scope posts wish_id", async () => {
    const fn = mockApi({ ...base, "/api/wishlist": [{ id: "w1", card_id: "c1", card: { name: "Charizard", number: "4" }, grading: null }],
      "/api/collection": { items: [], total: 0 }, "POST /api/alerts": { id: "n" } });
    renderPage(<Alerts />);
    await userEvent.click(await screen.findByRole("combobox", { name: "Scope" }));
    await userEvent.click(await screen.findByRole("option", { name: "a wishlist card" }));
    await userEvent.click(await screen.findByRole("button", { name: "Wishlist card" }));
    await userEvent.click(await screen.findByText("Charizard #4 · raw"));
    await userEvent.type(screen.getByLabelText("Amount"), "50");
    await userEvent.click(screen.getByRole("button", { name: /Add rule/ }));
    await waitFor(() => expect(posted(fn)).toMatchObject({ scope: "wish", wish_id: "w1", op: "above", threshold: 5000 }));
  });
  it("validates amount", async () => {
    mockApi({ ...base, "/api/collection": { items: [], total: 0 } });
    renderPage(<Alerts />);
    await userEvent.click(await screen.findByRole("button", { name: /Add rule/ }));
    expect(await screen.findByText("Enter an amount above 0")).toBeInTheDocument();
  });
  it("?stack= prefills the stack scope and its name", async () => {
    mockApi({ ...base, "/api/collection": { items: [stack], total: 1 } });
    renderPage(<Alerts />, "/alerts?stack=s1");
    await waitFor(() => expect(screen.getByRole("button", { name: "Stack" })).toHaveTextContent("Squirtle #7 · NM × 1"));
  });
});

describe("Alerts 'N new' label", () => {
  it("clears after Mark all read", async () => {
    let unread = 0;
    const ev = { id: "e1", type: "alert", name: "Mew", rule: "Stack above 10", value: 2000, read: false, fired_at: new Date().toISOString() };
    mockApi({
      "/api/alerts/events": () => [ev],
      "/api/alerts/unread-count": () => ({ count: unread }),
      "POST /api/alerts/evaluate": () => { unread = 1; return { fired: 1 }; },
      "POST /api/alerts/events/read": () => { unread = 0; ev.read = true; return { marked: 1 }; },
      "/api/alerts": [], "/api/collection": { items: [] },
    });
    renderPage(<Alerts />);
    await userEvent.click(await screen.findByRole("button", { name: "Check now" }));
    expect(await screen.findByText("1 new")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    await waitFor(() => expect(screen.queryByText("1 new")).not.toBeInTheDocument());
  });
});

describe("Settings", () => {
  const routes = { "/api/admin/status": { base_currency: "EUR", scheduler_enabled: false, price_sources: [] }, "/api/sets": [], "/api/admin/jobs": [], "/api/admin/fetcher-status": { up: false } };
  const pick = async () => {
    await userEvent.upload(document.querySelector('input[type="file"]')!, new File(["{}"], "c.json"));
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
  };
  it("shows created/updated/rejected summary", async () => {
    mockApi({ ...routes, "POST /api/collection/import": { created: 3, updated: 1, errors: [{ row: 2, error: "bad card" }] } });
    renderPage(<Settings />, "/settings?tab=data");
    await pick();
    expect(await screen.findByText(/Created 3, updated 1, 1 rejected/)).toBeInTheDocument();
    expect(screen.getByText("row 2: bad card")).toBeInTheDocument();
  });
  it("shows import error", async () => {
    mockApi({ ...routes, "POST /api/collection/import": { status: 413, body: { detail: "file too large" } } });
    renderPage(<Settings />, "/settings?tab=data");
    await pick();
    expect(await screen.findByText(/file too large/)).toBeInTheDocument();
  });
  const sets = [
    { external_id: "base1", name: "Base", series: "Base", release_date: "1999-01-09", cards_total: 102, cards_expected: 102, cards_missing: 0, cards_priced: 100 },
    { external_id: "sm11", name: "Unified Minds", series: "Sun & Moon", release_date: "2019-08-02", cards_total: 100, cards_expected: 260, cards_missing: 160, cards_priced: 90 },
    { external_id: "sm12", name: "Cosmic Eclipse", series: "Sun & Moon", release_date: "2019-11-01", cards_total: 0, cards_expected: 272, cards_missing: 0, cards_priced: 0 },
  ];
  it("catalog: groups by series, filters, selects, confirms import all", async () => {
    mockApi({ ...routes, "/api/sets": sets, "POST /api/admin/catalog/import": { started: true } });
    renderPage(<Settings />);
    expect(await screen.findByText("Sun & Moon")).toBeInTheDocument();
    expect(screen.queryByText("Unified Minds")).not.toBeInTheDocument(); // groups start collapsed
    await userEvent.click(screen.getByRole("button", { name: "Incomplete" }));
    expect(await screen.findByText("Unified Minds")).toBeInTheDocument();
    expect(screen.getByText("160 missing")).toBeInTheDocument();
    expect(screen.queryByText("Cosmic Eclipse")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Select Unified Minds" }));
    expect(screen.getByText("Selected sets (1)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Import all" }));
    expect(await screen.findByText("Import all sets?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start" }));
    await waitFor(() => expect(screen.queryByText("Import all sets?")).not.toBeInTheDocument());
  });
  it("jobs: readable summary and type filter", async () => {
    const now = new Date().toISOString();
    mockApi({ ...routes, "/api/admin/jobs": [
      { id: "1", type: "price_fetch", status: "ok", trigger: "manual", started_at: now, finished_at: now, stats: { total: 3, done: 3, ok: 2, not_found: 1, sales_new: 226 } },
      { id: "2", type: "catalog_import", status: "partial", trigger: "scheduler", started_at: now, finished_at: now, stats: { sets: 4, cards: 90, failed_sets: ["sm11"] } },
    ] });
    renderPage(<Settings />, "/settings?tab=jobs");
    expect(await screen.findByText("3/3 cards, 2 ok, 1 not found, 226 new sales")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Catalog import" }));
    expect(screen.queryByText(/226 new sales/)).not.toBeInTheDocument();
    expect(screen.getByText(/1 sets failed/)).toBeInTheDocument();
  });
  it("status error shows Retry", async () => {
    mockApi({ ...routes, "/api/admin/status": down });
    renderPage(<Settings />);
    expect(await screen.findByText(/Status: db down/)).toBeInTheDocument();
  });
});

describe("routing", () => {
  it("unknown route renders NotFound", () => {
    mockApi({ "/api/alerts/unread-count": { count: 0 } });
    renderPage(<Routes><Route path="*" element={<App />} /></Routes>, "/nope");
    expect(screen.getByText("Page not found")).toBeInTheDocument();
  });
});

const row = (over: object = {}) => ({ id: "s1", card_id: "pokemon:a-1", quantity: 2, language: "en", condition: "NM", grading: null, variant: null,
  card: { name: "Pikachu", number: "25", set: { name: "Base" }, images: {} }, value: 5000, cost: 3000, pl: 2000, price_kind: "market",
  needs_price: false, sources: {}, ...over });

describe("Collection table", () => {
  const routes = (calls: string[]) => ({ "/api/collection/summary": { ...summary, cards: 2, distinct: 1, value: 5000, cost: 3000, pl: 2000 },
    "/api/dashboard/history": [],
    "/api/collection": (_: unknown) => { calls.push("list"); return { items: [row()], total: 120 }; } });
  it("shows P/L, paging and sends sort + page to the API", async () => {
    const calls: string[] = [];
    const fn = mockApi(routes(calls));
    renderPage(<Collection />);
    expect(await screen.findByText("Pikachu")).toBeInTheDocument();
    expect(screen.getByText("1-50 of 120")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    await userEvent.click(screen.getByRole("button", { name: "P/L" }));
    await waitFor(() => {
      const urls = fn.mock.calls.map((c) => String(c[0])).filter((u) => u.includes("/api/collection?"));
      expect(urls.some((u) => u.includes("page=2"))).toBe(true);
      expect(urls.some((u) => u.includes("sort=pl") && u.includes("page=1"))).toBe(true); // sorting resets to page 1
    });
  });
  it("row click opens the details drawer with an alert shortcut", async () => {
    mockApi(routes([]));
    renderPage(<Collection />);
    await userEvent.click(await screen.findByRole("button", { name: "Details for Pikachu" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Create alert/ })).toHaveAttribute("href", "/alerts?stack=s1");
  });
  it("filters with no match say so", async () => {
    mockApi({ "/api/collection/summary": summary, "/api/dashboard/history": [], "/api/collection": { items: [], total: 0 } });
    renderPage(<Collection />, "/?graded=true");
    expect(await screen.findByText(/No stacks match these filters/)).toBeInTheDocument();
  });
});

describe("Collection needs price", () => {
  it("banner explains uncounted slabs and offers bulk fetch", async () => {
    mockApi({ "/api/collection/summary": { ...summary, cards: 1, distinct: 1, unpriced: 1, needs_price: 1, ref_raw_value: 8248 },
      "/api/collection": { items: [], total: 0 }, "/api/dashboard/history": [], "/api/admin/jobs": [], "/api/admin/fetcher-status": { up: true } });
    renderPage(<Collection />);
    expect(await screen.findByText(/not counted in Value or P\/L/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fetch missing prices" })).toBeEnabled();
  });
});
