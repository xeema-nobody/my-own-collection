import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { mockApi, renderPage } from "../test/utils";
import SourceStatus from "./SourceStatus";

const url = "https://alt.xyz/browse?query=Umbreon%20Gold%20Star%2017";
const routes = {
  "/api/cards/c1/fetch-status": { pricecharting: null, cardmarket_web: null, altxyz: { status: "ok", detail: null, url, fetched_at: "2026-11-02T10:00:00Z" } },
  "/api/cards/c1/match": { pricecharting: { url: null, candidates: [], product: null }, cardmarket_web: { url: null, candidates: [], product: null } },
};

describe("SourceStatus", () => {
  it("explains what alt.xyz searched and kept", async () => {
    mockApi(routes);
    const sales = [{ source: "altxyz", sold_at: "2026-10-20", title: "2021 Pokemon Celebrations Gold Star" }, { source: "altxyz", sold_at: "2026-10-25", title: "2021 Pokemon Celebrations Gold Star" }];
    renderPage(<SourceStatus cardId="c1" sales={sales} />);
    expect(await screen.findByText("Umbreon Gold Star 17")).toBeInTheDocument();
    expect(screen.getByText(/2 sold listings kept · last sale 2026-10-25/)).toBeInTheDocument();
    expect(screen.getByText(/×2/)).toBeInTheDocument();
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });
});
