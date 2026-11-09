import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CatalogTab from "./CatalogTab";

const audit = { sets: 3, cards: 20, promo_sets: 1, secret_over_printed: 2, provider_only: ["me6"], code_missing: [], to_import: ["me6"],
  rows: [{ id: "me6", name: "Delta Reign", promo: false, imported: 0, provider_total: 141, issues: ["new_at_provider"] }] };

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(audit), { status: 200, headers: { "content-type": "application/json" } })));
});

describe("coverage audit", () => {
  it("lists gaps and selects them for import", async () => {
    const setPicked = vi.fn();
    const q = (d: any) => ({ data: d, isLoading: false } as any);
    render(<QueryClientProvider client={new QueryClient()}><CatalogTab sets={q([])} jobs={q([])} picked={new Set()} setPicked={setPicked} /></QueryClientProvider>);
    await userEvent.click(screen.getByRole("button", { name: "Check coverage" }));
    expect(await screen.findByText("Delta Reign")).toBeTruthy();
    expect(screen.getByText("new at provider")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /Select gaps \(1\)/ }));
    expect(setPicked).toHaveBeenCalledWith(new Set(["me6"]));
  });
});
