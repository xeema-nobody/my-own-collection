import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import CardCollection from "./CardCollection";

const stack = (over: object = {}) => ({ id: "s1", variant: "holofoil", language: "en", condition: "NM", grading: null, quantity: 2, acquired: { price: 1500, currency: "EUR" }, ...over });
const card = (owned: object[] = []) => ({ _id: "pokemon:a-1", name: "Pikachu", variants: ["normal", "holofoil"], owned });
const base = (extra: Record<string, unknown> = {}) => mockApi({
  "/api/collection": { items: [{ id: "s1", value: 4200, estimated: false, needs_price: false }, { id: "s2", value: null, needs_price: true }], total: 2 },
  "/api/cards/pokemon%3Aa-1/compare": { value: 2100, estimated: false },
  ...extra });

describe("CardCollection owned", () => {
  it("rows show badge, value, paid and needs price; cert stack cannot be incremented", async () => {
    base();
    renderPage(<CardCollection card={card([stack(), stack({ id: "s2", condition: null, grading: { company: "PSA", grade: 10, cert_number: "123" }, quantity: 1, acquired: null })])} />);
    expect((await screen.findAllByText("NM")).length).toBeGreaterThan(1);
    expect(screen.getByText("PSA 10")).toBeInTheDocument();
    expect(await screen.findByText("needs price")).toBeInTheDocument();
    expect(screen.getByText(/^paid .*15/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Increase PSA 10 quantity" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Increase NM quantity" })).toBeEnabled();
  });
  it("remove asks to confirm, then deletes the stack", async () => {
    const calls: string[] = [];
    base({ "DELETE /api/collection/s1": () => { calls.push("del"); return { status: 204 }; } });
    renderPage(<CardCollection card={card([stack()])} />);
    await userEvent.click(await screen.findByRole("button", { name: "Remove NM stack" }));
    expect(calls).toEqual([]);
    expect(await screen.findByText(/Remove all/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Remove stack" }));
    await waitFor(() => expect(calls).toEqual(["del"]));
  });
  it("decrease stepper removes one copy", async () => {
    const bodies: unknown[] = [];
    base({ "POST /api/collection/s1/remove": (init?: RequestInit) => { bodies.push(JSON.parse(String(init?.body))); return {}; } });
    renderPage(<CardCollection card={card([stack()])} />);
    await userEvent.click(await screen.findByRole("button", { name: "Decrease NM quantity" }));
    await waitFor(() => expect(bodies).toEqual([{ quantity: 1 }]));
  });
});

describe("CardCollection add", () => {
  it("raw: posts condition, no grading; shows the estimate", async () => {
    const bodies: any[] = [];
    base({ "POST /api/collection": (init?: RequestInit) => { bodies.push(JSON.parse(String(init?.body))); return {}; } });
    renderPage(<CardCollection card={card()} />);
    await waitFor(() => expect(screen.getByTestId("estimate")).toHaveTextContent("21"));
    await userEvent.click(screen.getByRole("radio", { name: "LP" }));
    await userEvent.click(screen.getByRole("button", { name: "Increase Quantity to add" }));
    await userEvent.click(screen.getByRole("button", { name: /Add 2 copies/ }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ card_id: "pokemon:a-1", condition: "LP", grading: null, quantity: 2, variant: "normal" });
  });
  it("graded: switching hides condition, shows grader + grade, no price -> hint", async () => {
    const calls: string[] = [];
    base({ "/api/cards/pokemon%3Aa-1/compare": (_: unknown) => ({ value: null, needs_price: true }), "POST /api/collection": (init?: RequestInit) => { calls.push(String(init?.body)); return {}; } });
    renderPage(<CardCollection card={card()} />);
    await userEvent.click(screen.getByRole("radio", { name: "Graded" }));
    expect(screen.queryByRole("radio", { name: "LP" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Grader" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Grade" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("estimate")).toHaveTextContent(/No price for this grade yet/));
    await userEvent.click(screen.getByRole("button", { name: /Add to collection/ }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(JSON.parse(calls[0])).toMatchObject({ condition: null, grading: { company: "PSA", grade: 9, cert_number: null } });
  });
});
