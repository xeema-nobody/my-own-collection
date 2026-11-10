import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import JaSets from "./JaSets";

const rows = [{ id: "SV2a", name: "ポケモンカード151", total: 210, printed_total: 165, imported: 0 },
  { id: "S12a", name: "VSTARユニバース", total: 258, printed_total: 172, imported: 258 }];
let calls: string[] = [];

beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push(`${init?.method ?? "GET"} ${url}`);
    return new Response(JSON.stringify(url.includes("/import") ? { started: true } : rows), { status: init?.method === "POST" ? 202 : 200, headers: { "content-type": "application/json" } });
  }));
});

const mount = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
  <JaSets jobs={{ data: [] } as any} /></QueryClientProvider>);

describe("JaSets", () => {
  it("loads sets only on click, shows state, imports the picked ones", async () => {
    mount();
    expect(calls).toEqual([]);                                   // no live request until asked
    await userEvent.click(screen.getByText("Load Japanese sets"));
    expect(await screen.findByText("not imported")).toBeTruthy();
    expect(screen.getByText("complete")).toBeTruthy();
    await userEvent.click(screen.getByLabelText("Select ポケモンカード151"));
    await userEvent.click(screen.getByText("Import selected (1)"));
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST") && c.includes("/api/admin/catalog/ja/import") && c.includes("sets=SV2a"))).toBe(true));
  });

  it("filters by code", async () => {
    mount();
    await userEvent.click(screen.getByText("Load Japanese sets"));
    await screen.findByText("not imported");
    await userEvent.type(screen.getByLabelText("Filter Japanese sets"), "S12a");
    expect(screen.queryByLabelText("Select ポケモンカード151")).toBeNull();
    expect(screen.getByLabelText("Select VSTARユニバース")).toBeTruthy();
  });
});
