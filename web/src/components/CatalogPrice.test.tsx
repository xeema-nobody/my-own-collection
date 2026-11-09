import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import CatalogPrice from "./CatalogPrice";

describe("CatalogPrice", () => {
  it("says an untracked, unpriced card has no price and fetches just that card", async () => {
    const calls = mockApi({ "POST /api/cards/c1/refresh-price": { found: true, prices: 3, tracked: false } });
    renderPage(<CatalogPrice card={{ id: "c1", owned: [] }} />);
    expect(screen.getByText(/No price \(not tracked\)/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Fetch price" }));
    expect(await screen.findByText("Catalog price fetched.")).toBeInTheDocument();
    expect(calls).toHaveBeenCalledTimes(1);
  });

  it("renders nothing for a priced card", () => {
    mockApi({});
    const { container } = renderPage(<CatalogPrice card={{ id: "c1", owned: [], price_base: 500 }} />);
    expect(container.textContent).toBe("");
  });
});
