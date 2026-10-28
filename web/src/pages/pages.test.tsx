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
const summary = { cards: 0, distinct: 0, value: 0, cost: 0, pl: null, unpriced: 0, estimated: 0, by_source: {}, value_by_kind: {} };

describe("Collection", () => {
  it("empty state", async () => {
    mockApi({ "/api/collection/summary": summary, "/api/collection": { items: [], total: 0 } });
    renderPage(<Collection />);
    expect(await screen.findByText(/Nothing here/)).toBeInTheDocument();
  });
  it("API error shows alert", async () => {
    mockApi({ "/api/collection/summary": down, "/api/collection": down });
    renderPage(<Collection />);
    expect(await screen.findAllByRole("alert")).toHaveLength(2);
    expect(screen.getAllByText(/db down/).length).toBe(2);
  });
});

describe("Dashboard", () => {
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
    expect(screen.getByText("No rules yet.")).toBeInTheDocument();
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

describe("Settings import", () => {
  const routes = { "/api/admin/status": { base_currency: "EUR", scheduler_enabled: false, price_sources: [] }, "/api/sets": [], "/api/admin/jobs": [], "/api/admin/fetcher-status": { up: false } };
  const pick = async () => {
    await userEvent.upload(document.querySelector('input[type="file"]')!, new File(["{}"], "c.json"));
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
  };
  it("shows created/updated/rejected summary", async () => {
    mockApi({ ...routes, "POST /api/collection/import": { created: 3, updated: 1, errors: [{ row: 2, error: "bad card" }] } });
    renderPage(<Settings />);
    await pick();
    expect(await screen.findByText(/Created 3, updated 1, 1 rejected/)).toBeInTheDocument();
    expect(screen.getByText("row 2: bad card")).toBeInTheDocument();
  });
  it("shows import error", async () => {
    mockApi({ ...routes, "POST /api/collection/import": { status: 413, body: { detail: "file too large" } } });
    renderPage(<Settings />);
    await pick();
    expect(await screen.findByText(/file too large/)).toBeInTheDocument();
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
