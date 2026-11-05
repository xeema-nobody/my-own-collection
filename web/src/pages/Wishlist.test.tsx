import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import Wishlist from "./Wishlist";

const entry = (o: object = {}) => ({
  id: "w1", card_id: "pokemon:a-1", variant: null, grading: null, target_price: 8000, note: "holo", alert: true,
  card: { _id: "pokemon:a-1", name: "Charizard", number: "4", set: { name: "Base" }, images: {} },
  value: 7500, estimated: false, price_kind: "market", needs_price: false, gap: -500, hit: true, ...o });

describe("Wishlist page", () => {
  it("empty state", async () => {
    mockApi({ "/api/wishlist": [] });
    renderPage(<Wishlist />);
    expect(await screen.findByText("Nothing on your wishlist")).toBeInTheDocument();
  });
  it("rows show price, target, hit badge and graded version", async () => {
    mockApi({ "/api/wishlist": [entry(), entry({ id: "w2", grading: { company: "PSA", grade: 9 }, value: null, needs_price: true, gap: null, hit: false })] });
    renderPage(<Wishlist />);
    expect(await screen.findByText(/target hit · .*5\.00 under/)).toBeInTheDocument();
    expect(screen.getByText("PSA 9")).toBeInTheDocument();
    expect(screen.getByText("needs price")).toBeInTheDocument();
  });
  it("Target hit chip filters", async () => {
    mockApi({ "/api/wishlist": [entry(), entry({ id: "w2", note: "second", hit: false, gap: 100 })] });
    renderPage(<Wishlist />);
    await screen.findByText("holo");
    await userEvent.click(screen.getByRole("button", { name: "Target hit" }));
    expect(screen.queryByText("second")).not.toBeInTheDocument();
    expect(screen.getByText("holo")).toBeInTheDocument();
  });
  it("search narrows the list and sort reorders it (state lives in the URL)", async () => {
    mockApi({ "/api/wishlist": [entry({ id: "w1", value: 100, card: { _id: "a", name: "Charizard", number: "4", set: { name: "Base" }, images: {} } }),
      entry({ id: "w2", value: 900, note: "second", card: { _id: "b", name: "Blastoise", number: "2", set: { name: "Base" }, images: {} } })], "/api/collection/presets": [] });
    renderPage(<Wishlist />, "/?sort=value&order=asc");
    await screen.findByText("Charizard #4");
    const names = () => screen.getAllByRole("link").map((a) => /(\w+ #\d+)/.exec(a.textContent ?? "")?.[1]).filter(Boolean);
    expect(names()).toEqual(["Charizard #4", "Blastoise #2"]);          // value ascending from the URL
    await userEvent.type(screen.getByLabelText("Search wishlist"), "blast");
    expect(names()).toEqual(["Blastoise #2"]);
  });
  it("grid view lists the entries and is remembered", async () => {
    localStorage.clear();
    mockApi({ "/api/wishlist": [entry(), entry({ id: "w2", note: "second" })], "/api/collection/presets": [] });
    renderPage(<Wishlist />);
    await screen.findAllByText("Charizard #4");
    await userEvent.click(screen.getByRole("radio", { name: /Grid/ }));
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(localStorage.getItem("wishlist.view")).toBe("grid");
  });
  it("remove asks to confirm, then deletes", async () => {
    const calls: string[] = [];
    mockApi({ "/api/wishlist": [entry()], "DELETE /api/wishlist/w1": () => { calls.push("del"); return { status: 204 }; } });
    renderPage(<Wishlist />);
    await userEvent.click(await screen.findByRole("button", { name: "Remove Charizard raw" }));
    expect(calls).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(calls).toEqual(["del"]));
  });
  it("edit saves target in cents", async () => {
    let body: any;
    mockApi({ "/api/wishlist": [entry()], "PATCH /api/wishlist/w1": (init?: RequestInit) => { body = JSON.parse(String(init?.body)); return entry(); } });
    renderPage(<Wishlist />);
    await userEvent.click(await screen.findByRole("button", { name: "Edit Charizard raw" }));
    const input = await screen.findByLabelText("Target price (€)");
    await userEvent.clear(input);
    await userEvent.type(input, "65.5");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).toMatchObject({ target_price: 6550, alert: true }));
  });
  it("has Fetch all prices defaulting to the wishlist scope, plus freshness counts", async () => {
    mockApi({ "/api/wishlist": [entry()], "/api/wishlist/prices": { cards: 4, fresh: 2, stale: 1, never: 1, fresh_days: 7 },
      "/api/admin/jobs": [], "/api/admin/fetcher-status": { up: true, sites: {} } });
    renderPage(<Wishlist />);
    expect(await screen.findByRole("button", { name: "Fetch all prices" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Wishlist" })).toBeChecked();
    expect(await screen.findByText("2 fresh (≤7 d)")).toBeInTheDocument();
    expect(screen.getByText("1 never fetched")).toBeInTheDocument();
  });
});
