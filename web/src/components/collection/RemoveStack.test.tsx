import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import RemoveStack from "./RemoveStack";

afterEach(() => vi.restoreAllMocks());

const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

it("sends reason, price in cents and quantity", async () => {
  const f = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ deleted: false, quantity: 1, removed: 1 }), text: async () => "{}" });
  vi.stubGlobal("fetch", f);
  const done = vi.fn();
  wrap(<RemoveStack id="s1" quantity={2} name="Mew" onDone={done} />);
  await userEvent.click(screen.getByRole("button", { name: "Sell / remove" }));
  await userEvent.type(screen.getByLabelText("Sale price"), "12.5");
  await userEvent.click(screen.getByRole("button", { name: "Mark sold" }));
  await waitFor(() => expect(done).toHaveBeenCalled());
  const [url, init] = f.mock.calls[0];
  expect(url).toContain("/api/collection/s1/remove");
  expect(JSON.parse(init.body)).toMatchObject({ quantity: 1, reason: "sold", price: 1250 });
});

it("gifted hides the price and warns on whole stack", async () => {
  wrap(<RemoveStack id="s1" quantity={1} name="Mew" />);
  await userEvent.click(screen.getByRole("button", { name: "Sell / remove" }));
  await userEvent.click(screen.getByRole("radio", { name: "Gifted" }));
  expect(screen.queryByLabelText("Sale price")).toBeNull();
  expect(screen.getByText(/whole stack/)).toBeTruthy();
});
