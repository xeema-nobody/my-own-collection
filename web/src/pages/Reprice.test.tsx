import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import Reprice from "./Reprice";

const row = (o: object = {}) => ({
  item_id: "s1", card_id: "pokemon:a-1", name: "Spiritomb", set: "Lost Origin", number: "TG09", grade_key: "raw", quantity: 1,
  platform: "vinted", url: "https://www.vinted.nl/items/1-x", currency: "EUR", asking_price: 400, market: 500, change_pct: 25,
  change_amount: 100, suggested: 550, needs_platform_update: false, warnings: [], last_sold: null, ...o });
const table = (rows: object[]) => ({ markup_pct: 10, threshold_pct: 5, rows });

describe("Reprice page", () => {
  it("empty state", async () => {
    mockApi({ "/api/reprice": table([]) });
    renderPage(<Reprice />);
    expect(await screen.findByText("Nothing listed")).toBeInTheDocument();
  });

  it("suggested price prefilled, edit + Confirm sends cents for that platform", async () => {
    const f = mockApi({ "/api/reprice": table([row()]), "POST /api/reprice/confirm": { id: "s1" } });
    renderPage(<Reprice />);
    const input = await screen.findByLabelText("Suggested Spiritomb vinted") as HTMLInputElement;
    expect(input.value).toBe("5.50");
    await userEvent.clear(input);
    await userEvent.type(input, "4,75");
    await userEvent.click(screen.getByRole("button", { name: /Confirm/ }));
    await waitFor(() => expect(f.mock.calls.some(([, i]) => i?.method === "POST")).toBe(true));
    const call = f.mock.calls.find(([u]) => String(u).includes("/api/reprice/confirm"))!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({ item_id: "s1", platform: "vinted", asking_price: 475 });
  });

  it("no market price: empty suggestion, Confirm disabled; flagged Vinted row offers Update on Vinted", async () => {
    mockApi({ "/api/reprice": table([row({ market: null, suggested: null, change_pct: null, change_amount: null, warnings: ["no market price"] }),
      row({ item_id: "s2", name: "Kleavor V", needs_platform_update: true, last_sold: { price: 300, currency: "EUR", price_base: 300, source: "altxyz", sold_at: "2026-11-10", condition_unknown: true } })]) });
    renderPage(<Reprice />);
    expect(await screen.findByText("no price")).toBeInTheDocument();
    expect((screen.getByLabelText("Suggested Spiritomb vinted") as HTMLInputElement).value).toBe("");
    expect((screen.getAllByRole("button", { name: /Confirm/ })[0] as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("condition unknown")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update on Vinted" })).toBeInTheDocument();
  });
});
