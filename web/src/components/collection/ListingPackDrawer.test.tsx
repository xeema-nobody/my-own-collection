import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import ListingPackDrawer from "./ListingPackDrawer";

afterEach(() => vi.restoreAllMocks());
const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

const PACK = { platform: "vinted", strategy: "market", pct: 5, missing: [], items: [
  { item_id: "s1", card_id: "pokemon:a-1", title: "Charizard - Base 4 - Near Mint", description: "Charizard\nCondition: Near Mint", price: 1250, currency: "EUR", quantity: 1, photos: ["p1"], warnings: [],
    sale: { status: "listed", listings: [{ platform: "ebay", asking_price: 2000, currency: "EUR" }] } },
  { item_id: "s2", card_id: "pokemon:a-2", title: "Mew", description: "Mew", price: null, currency: "EUR", quantity: 1, photos: [], warnings: ["needs price: no market price for this stack", "no photos"] }] };

function stub() {
  const f = vi.fn(async (url: string, init?: RequestInit) => ({ ok: true, status: 200, json: async () => (String(url).includes("listing-pack") ? PACK : { id: "s1", sale: {} }), text: async () => "{}" }));
  vi.stubGlobal("fetch", f);
  return f;
}

it("shows the pack with warnings and an empty price for an unpriced stack", async () => {
  stub();
  wrap(<ListingPackDrawer ids={["s1", "s2"]} open onClose={() => {}} />);
  expect(await screen.findByDisplayValue("Charizard - Base 4 - Near Mint")).toBeTruthy();
  expect((screen.getByLabelText("Price 1") as HTMLInputElement).value).toBe("12.50");
  expect((screen.getByLabelText("Price 2") as HTMLInputElement).value).toBe("");
  expect(screen.getByText(/needs price/)).toBeTruthy();
});

it("Mark as Listed sends the edited price in cents, keeps other platforms, skips the unpriced stack", async () => {
  const f = stub();
  wrap(<ListingPackDrawer ids={["s1", "s2"]} open onClose={() => {}} />);
  const price = await screen.findByLabelText("Price 1");
  await userEvent.clear(price);
  await userEvent.type(price, "11.9");
  await userEvent.click(screen.getByRole("button", { name: /Mark as Listed on Vinted/ }));
  await waitFor(() => expect(screen.getByText(/Marked 1 stack/)).toBeTruthy());
  const puts = f.mock.calls.filter(([, i]) => i?.method === "PUT");
  expect(puts).toHaveLength(1);
  expect(puts[0][0]).toContain("/api/collection/s1/sale");
  const body = JSON.parse(String(puts[0][1]!.body));
  expect(body.status).toBe("listed");
  expect(body.listings).toMatchObject([{ platform: "ebay", asking_price: 2000 }, { platform: "vinted", asking_price: 1190 }]);
});
