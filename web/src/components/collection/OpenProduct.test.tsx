import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import OpenProduct from "./OpenProduct";
import { exitLabel } from "./RemoveStack";

afterEach(() => vi.restoreAllMocks());

const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
const reply = (body: unknown) => vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => body, text: async () => "{}" });

it("opens units with date, extras and note, then shows the result", async () => {
  const f = reply({ opening_id: "o1", opened: 2, left: 1, stack_deleted: false, pulled: [] });
  vi.stubGlobal("fetch", f);
  wrap(<OpenProduct id="s1" quantity={3} name="Booster Box" />);
  await userEvent.click(screen.getByRole("button", { name: "Open product" }));
  await userEvent.clear(screen.getByLabelText("Units opened"));
  await userEvent.type(screen.getByLabelText("Units opened"), "2");
  await userEvent.type(screen.getByLabelText("Extras"), "code card, coin");
  await userEvent.click(screen.getByRole("button", { name: "Mark opened (2)" }));
  await screen.findByText(/Opened 2 × Booster Box, 1 left/);
  const [url, init] = f.mock.calls[0];
  expect(url).toContain("/api/collection/s1/open");
  expect(JSON.parse(init.body)).toMatchObject({ quantity: 2, extras: "code card, coin", pulled: [] });
});

it("caps units at the stack and warns when it opens the whole stack", async () => {
  wrap(<OpenProduct id="s1" quantity={2} name="ETB" />);
  await userEvent.click(screen.getByRole("button", { name: "Open product" }));
  await userEvent.clear(screen.getByLabelText("Units opened"));
  await userEvent.type(screen.getByLabelText("Units opened"), "9");
  expect(screen.getByRole("button", { name: "Mark opened (2)" })).toBeTruthy();
  expect(screen.getByText(/opens the whole stack/)).toBeTruthy();
});

it("history label for the opened reason", () => {
  expect(exitLabel("opened")).toBe("Opened");
});
