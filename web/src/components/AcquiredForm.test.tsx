import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AcquiredForm, { buildPatch } from "./AcquiredForm";

const st = (o: object = {}) => ({ type: "", price: "", total: false, currency: "EUR", date: "", source: "", ...o });

describe("buildPatch", () => {
  it("edit sends every field; blank clears", () => {
    expect(buildPatch(st({ type: "purchased", price: "12.50", source: " shop " }), 3, false))
      .toEqual({ type: "purchased", price: 1250, currency: "EUR", date: null, source: "shop" });
    expect(buildPatch(st(), 1, false)).toEqual({ type: null, price: null, currency: "EUR", date: null, source: null });
  });
  it("total entry stores the rounded per-copy average", () => {
    expect(buildPatch(st({ price: "10", total: true }), 3, false).price).toBe(333);
  });
  it("bulk leaves blank fields out so they keep their value", () => {
    expect(buildPatch(st({ type: "pulled", currency: "" }), 5, true)).toEqual({ type: "pulled" });
    expect(buildPatch(st({ price: "0", currency: "USD" }), 5, true)).toEqual({ price: 0, currency: "USD" });
  });
});

describe("AcquiredForm", () => {
  it("submits edited values, picking Pulled fills price 0", async () => {
    const onSubmit = vi.fn();
    render(<AcquiredForm initial={null} qty={1} onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole("combobox", { name: "Acquired how" }));
    await userEvent.click(await screen.findByRole("option", { name: "Pulled" }));
    expect(screen.getByLabelText("Price")).toHaveValue(0);
    await userEvent.type(screen.getByLabelText("Where bought"), "booster");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onSubmit).toHaveBeenCalledWith({ type: "pulled", price: 0, currency: "EUR", date: null, source: "booster" });
  });
  it("total mode shows the stored per-copy price", async () => {
    render(<AcquiredForm initial={{ price: 100 }} qty={3} onSubmit={() => {}} />);
    await userEvent.click(screen.getByRole("radio", { name: "Total for 3" }));
    await userEvent.clear(screen.getByLabelText("Price"));
    await userEvent.type(screen.getByLabelText("Price"), "10");
    expect(screen.getByText("= 3.33 per copy")).toBeInTheDocument();
  });
  it("bulk mode has no total toggle", () => {
    render(<AcquiredForm bulk qty={3} onSubmit={() => {}} />);
    expect(screen.queryByRole("radio", { name: /Total for/ })).toBeNull();
  });
});

describe("AcquiredForm controlled by a parent (onChange + hideSubmit)", () => {
  it("reports the patch on every edit and has no submit button", async () => {
    const onChange = vi.fn();
    render(<AcquiredForm hideSubmit onChange={onChange} />);
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    await userEvent.type(screen.getByLabelText("Price"), "5");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ price: 500, currency: "EUR" }));
  });
});
