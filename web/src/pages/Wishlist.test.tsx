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
});
