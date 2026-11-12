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

function renderQueue(rows: unknown[]) {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => rows, text: async () => "{}" })));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><PublishQueueView /></QueryClientProvider>);
}

it("Publish waiting opens the Vinted create page with the extension hash", async () => {
  const open = vi.fn();
  vi.stubGlobal("open", open);
  renderQueue([e("1", "confirmed"), e("2", "confirmed"), e("3", "published")]);
  await userEvent.click(await screen.findByRole("button", { name: "Publish waiting (2)" }));
  expect(open).toHaveBeenCalledWith("https://www.vinted.nl/items/new#moc-publish", "_blank");
});

it("Publish waiting is disabled when nothing is waiting", async () => {
  renderQueue([e("1", "publishing"), e("2", "published")]);
  expect(((await screen.findByRole("button", { name: "Publish waiting" })) as HTMLButtonElement).disabled).toBe(true);
});
