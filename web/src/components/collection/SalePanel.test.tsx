import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import SalePanel, { SaleBadge } from "./SalePanel";
import RemoveStack from "./RemoveStack";

afterEach(() => vi.restoreAllMocks());
const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
const ok = (body: unknown) => vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => body, text: async () => "{}" });

it("listing needs a price, sends cents and the platform", async () => {
  const f = ok({ id: "s1", sale: { status: "listed", listings: [] } });
  vi.stubGlobal("fetch", f);
  wrap(<SalePanel id="s1" sale={null} />);
  await userEvent.click(screen.getByRole("button", { name: "Edit sale" }));
  await userEvent.click(screen.getByRole("combobox", { name: "Sale status" }));
  await userEvent.click(screen.getByRole("option", { name: "Listed" }));
  await userEvent.click(screen.getByRole("button", { name: "Add listing" }));
  expect((screen.getByRole("button", { name: "Save sale" }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.type(screen.getByLabelText("Asking price 1"), "12.5");
  await userEvent.click(screen.getByRole("button", { name: "Save sale" }));
  await waitFor(() => expect(f).toHaveBeenCalled());
  const [url, init] = f.mock.calls[0];
  expect(url).toContain("/api/collection/s1/sale");
  expect(init.method).toBe("PUT");
  expect(JSON.parse(init.body)).toMatchObject({ status: "listed", listings: [{ platform: "vinted", asking_price: 1250 }] });
});

it("badge shows status and platforms, nothing for not-for-sale", () => {
  const { container, rerender } = render(<SaleBadge sale={{ status: "listed", listings: [{ platform: "vinted", asking_price: 100, currency: "EUR" }] }} />);
  expect(container.textContent).toContain("Listed · Vinted");
  rerender(<SaleBadge sale={{ status: "none", listings: [] }} />);
  expect(container.textContent).toBe("");
});

it("sold sends platform, fees and shipping in cents and shows the delist warning", async () => {
  const f = ok({ deleted: true, quantity: 0, removed: 1, realised: 400, delist: ["ebay"] });
  vi.stubGlobal("fetch", f);
  wrap(<RemoveStack id="s1" quantity={1} name="Mew" cost={500} />);
  await userEvent.click(screen.getByRole("button", { name: "Sell / remove" }));
  await userEvent.type(screen.getByLabelText("Sale price"), "10");
  await userEvent.type(screen.getByLabelText("Fees"), "0.8");
  await userEvent.type(screen.getByLabelText("Shipping paid"), "0.2");
  await userEvent.click(screen.getByRole("button", { name: "Mark sold" }));
  await waitFor(() => expect(screen.getByText(/Delist from: ebay/)).toBeTruthy());
  expect(JSON.parse(f.mock.calls[0][1].body)).toMatchObject({ price: 1000, fees: 80, shipping_paid: 20 });
});

const queueStub = (entries: unknown[]) => vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => entries, text: async () => "[]" })));

it("Vinted block: Publish button when never published, opens the Publish table by id", async () => {
  queueStub([]);
  const onPublish = vi.fn();
  wrap(<SalePanel id="s1" sale={null} onPublish={onPublish} />);
  expect(await screen.findByText("Not published")).toBeTruthy();
  await userEvent.click(screen.getByRole("button", { name: "Publish on Vinted" }));
  expect(onPublish).toHaveBeenCalledWith("s1");
});

it("Vinted block: waiting item disables the button, listed stack offers Update with the link", async () => {
  queueStub([{ id: "q1", item_id: "s1", state: "confirmed", mode: "update", url: null, error: null, photos: 1, payload: {}, updated_at: "" }]);
  wrap(<SalePanel id="s1" sale={{ status: "listed", listings: [{ platform: "vinted", asking_price: 500, currency: "EUR", url: "https://www.vinted.nl/items/9-x" }] }} onPublish={() => {}} />);
  expect(await screen.findByText(/Waiting for the Claude session/)).toBeTruthy();
  expect((screen.getByRole("button", { name: "Update on Vinted" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole("link", { name: "Vinted item" }).getAttribute("href")).toBe("https://www.vinted.nl/items/9-x");
});
