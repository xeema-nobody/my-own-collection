import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import CardWishlist from "./CardWishlist";

const card = { _id: "pokemon:a-1", name: "Pikachu" };

describe("CardWishlist", () => {
  it("lists entries of the card with hit badge", async () => {
    mockApi({ "/api/wishlist": [{ id: "w1", grading: { company: "PSA", grade: 10 }, value: 9000, estimated: false, target_price: 9500, hit: true, needs_price: false }] });
    renderPage(<CardWishlist card={card} />);
    expect(await screen.findByText("PSA 10")).toBeInTheDocument();
    expect(screen.getByText("target hit")).toBeInTheDocument();
  });
  it("adds a raw want with target in cents and fetches prices", async () => {
    let body: any;
    const fn = mockApi({ "/api/wishlist": [], "POST /api/wishlist": (init?: RequestInit) => { body = JSON.parse(String(init?.body)); return { id: "w9" }; },
      "POST /api/cards/pokemon%3Aa-1/fetch-prices": { started: true, cards: 1 } });
    renderPage(<CardWishlist card={card} />);
    await userEvent.type(await screen.findByLabelText("Target price (€)"), "12.5");
    await userEvent.click(screen.getByRole("button", { name: /Add to wishlist/ }));
    await waitFor(() => expect(body).toEqual({ card_id: "pokemon:a-1", grading: null, target_price: 1250, alert: true }));
    expect(await screen.findByText(/Saved. Fetching prices/)).toBeInTheDocument();
    expect(fn).toHaveBeenCalled();
  });
  it("graded want posts company and grade; bad target is rejected client side", async () => {
    let body: any;
    mockApi({ "/api/wishlist": [], "POST /api/wishlist": (init?: RequestInit) => { body = JSON.parse(String(init?.body)); return { id: "w9" }; },
      "POST /api/cards/pokemon%3Aa-1/fetch-prices": { status: 503, body: { detail: "off" } } });
    renderPage(<CardWishlist card={card} />);
    await userEvent.click(await screen.findByRole("radio", { name: "Graded" }));
    await userEvent.type(screen.getByLabelText("Target price (€)"), "0");
    await userEvent.click(screen.getByRole("button", { name: /Add to wishlist/ }));
    expect(await screen.findByText("Target must be above 0 (or empty)")).toBeInTheDocument();
    expect(body).toBeUndefined();
    await userEvent.clear(screen.getByLabelText("Target price (€)"));
    await userEvent.click(screen.getByRole("button", { name: /Add to wishlist/ }));
    await waitFor(() => expect(body).toMatchObject({ grading: { company: "PSA", grade: 9 }, alert: true }));
    expect(body.target_price).toBeUndefined();
  });
});
