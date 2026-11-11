import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import PublishQueueView from "./PublishQueue";

afterEach(() => vi.restoreAllMocks());
const e = (id: string, state: string, extra = {}) => ({ id, item_id: "s" + id, state, mode: "create", url: null, error: null, photos: 2, updated_at: "",
  payload: { title: "Card " + id, price: 300, currency: "EUR" }, ...extra });

it("lists every state with Cancel / Release / Retry and posts the action", async () => {
  const f = vi.fn(async (_u: string, init?: RequestInit) => ({ ok: true, status: 200, json: async () => (init?.method === "POST" ? {} : [e("1", "confirmed"), e("2", "publishing"), e("3", "failed", { error: "boom" }), e("4", "cancelled")]), text: async () => "{}" }));
  vi.stubGlobal("fetch", f);
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><PublishQueueView /></QueryClientProvider>);
  expect(await screen.findByText(/Card 1/)).toBeTruthy();
  expect(screen.getByText("Cancelled")).toBeTruthy();
  expect(screen.getByText("boom")).toBeTruthy();
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(f.mock.calls.some(([u, i]) => String(u).endsWith("/api/publish/queue/3/retry") && i?.method === "POST")).toBe(true));
  expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Release" })).toBeTruthy();
});
