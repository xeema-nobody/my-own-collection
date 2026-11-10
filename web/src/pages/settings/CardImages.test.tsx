import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CardImages from "./CardImages";

let calls: string[] = [];
beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push(`${init?.method ?? "GET"} ${url}`);
    const body = url.includes("/status") ? { legacy: 120, restorable: 3, top_sets: [] } : { started: true };
    return new Response(JSON.stringify(body), { status: init?.method === "POST" ? 202 : 200, headers: { "content-type": "application/json" } });
  }));
});

const mount = (jobs: any[] = []) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
  <CardImages jobs={{ data: jobs } as any} /></QueryClientProvider>);

describe("CardImages", () => {
  it("shows the remaining count and starts the move", async () => {
    mount();
    expect(await screen.findByText("120 cards on images.pokemontcg.io")).toBeTruthy();
    await userEvent.click(screen.getByText("Move to TCGdex"));
    await waitFor(() => expect(calls.some((c) => c.startsWith("POST") && c.endsWith("/api/admin/catalog/images/repoint"))).toBe(true));
  });

  it("disables the move while the job runs", async () => {
    mount([{ type: "catalog_images", status: "running" }]);
    await screen.findByText("120 cards on images.pokemontcg.io");
    expect((screen.getByText("Moving…") as HTMLButtonElement).disabled).toBe(true);
  });
});
