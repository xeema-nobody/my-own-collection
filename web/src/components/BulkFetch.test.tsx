import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { mockApi, renderPage } from "../test/utils";
import BulkFetch from "./BulkFetch";
import FetchProgress from "./FetchProgress";
import { etaText } from "../lib/fetchJob";

const base = { done: 42, total: 120, ok: 39, failed: 3, needs_match: 0, not_found: 0, skipped_cached: 0, skipped_site: 0, sales_new: 0, seeded: 0,
  failures: [], needs_match_list: [], waiting_login: [], current: { card_id: "c1", source: "altxyz" }, paused: false, eta_s: 360, mode: "all" };
const running = (stats = {}) => ({ id: "j1", type: "price_fetch", status: "running", stats: { ...base, ...stats } });
const routes = (jobs: unknown[], extra: Record<string, unknown> = {}) => ({
  "/api/admin/jobs": jobs, "/api/admin/fetcher-status": { up: true, sites: {} }, ...extra });

describe("etaText", () => {
  it("formats pace", () => {
    expect(etaText(null)).toBeNull();
    expect(etaText(30)).toBe("<1 min left");
    expect(etaText(360)).toBe("~6 min left");
    expect(etaText(3 * 3600)).toBe("~3.0 h left");
  });
});

describe("BulkFetch", () => {
  it("starts a stale-mode run with the chosen days", async () => {
    const fn = mockApi(routes([], { "POST /api/admin/prices/fetch": { started: true, cards: 3 } }));
    renderPage(<BulkFetch />);
    fireEvent.click(screen.getByRole("radio", { name: "Stale" }));
    fireEvent.change(screen.getByLabelText("Stale after days"), { target: { value: "14" } });
    fireEvent.click(screen.getByRole("button", { name: "Fetch all prices" }));
    await waitFor(() => expect(fn.mock.calls.some(([u, i]) => String(u).endsWith("/prices/fetch") && (i as RequestInit)?.method === "POST")).toBe(true));
    const call = fn.mock.calls.find(([u, i]) => String(u).endsWith("/prices/fetch") && (i as RequestInit)?.method === "POST")!;
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({ mode: "stale", stale_days: 14 });
  });

  it("shows pace of a job already running (after leaving and returning) and disables the button", async () => {
    mockApi(routes([running()]));
    renderPage(<BulkFetch />);
    expect(await screen.findByText(/42 \/ 120 done, 3 failed, ~6 min left/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fetch all prices" })).toBeDisabled();
  });

  it("explains a missing fetcher", async () => {
    mockApi(routes([], { "POST /api/admin/prices/fetch": { status: 503, body: { detail: "down" } } }));
    renderPage(<BulkFetch />);
    fireEvent.click(screen.getByRole("button", { name: "Fetch all prices" }));
    expect(await screen.findByText(/Fetcher not reachable/)).toBeInTheDocument();
  });
});

describe("FetchProgress", () => {
  it("pauses, resumes and cancels via the control endpoint", async () => {
    const fn = mockApi({ "POST /api/admin/prices/fetch/control": { ok: true }, "/api/admin/jobs": [] });
    const last = () => JSON.parse((fn.mock.calls.at(-1)![1] as RequestInit).body as string);
    const { unmount } = renderPage(<FetchProgress job={running()} live />);
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    await waitFor(() => expect(last()).toEqual({ action: "pause" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(last()).toEqual({ action: "cancel" }));
    unmount();
    renderPage(<FetchProgress job={running({ paused: true })} live />);
    expect(screen.getByText(/Paused/)).toBeInTheDocument();
    expect(screen.queryByText(/min left/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resume" }));
    await waitFor(() => expect(last()).toEqual({ action: "resume" }));
  });

  it("finish summary, failure reasons, match link and retry", async () => {
    const fn = mockApi({ "POST /api/admin/prices/fetch/retry": { started: true, cards: 1 }, "/api/admin/jobs": [] });
    const job = { id: "j1", status: "partial", stats: { ...base, done: 120, eta_s: null, ok_cards: 118, failed: 1, needs_match: 1,
      failures: [{ card_id: "pokemon:a-1", name: "Mew ex", source: "altxyz", reason: "layout changed", detail: "no price table" }],
      needs_match_list: [{ card_id: "pokemon:a-2", name: "Umbreon", source: "pricecharting", reason: "no match" }] } };
    renderPage(<FetchProgress job={job} live={false} />);
    expect(screen.getByRole("status")).toHaveTextContent("118 cards updated, 2 need attention");
    expect(screen.getByText("layout changed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose match" })).toHaveAttribute("href", "/cards/pokemon%3Aa-2#card-sources");
    fireEvent.click(screen.getByRole("button", { name: "Retry failed" }));
    await waitFor(() => expect(fn.mock.calls.some(([u]) => String(u).endsWith("/prices/fetch/retry"))).toBe(true));
  });
});
