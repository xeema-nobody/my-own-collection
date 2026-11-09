import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderPage } from "../../test/utils";
import AddSheet from "./AddSheet";
import type { ScanCard } from "../../lib/api";

const card: ScanCard = { id: "pokemon:base1-4", name: "Charizard", number: "4", printed_total: 102, set: { id: "base1", name: "Base" }, year: 1999, rarity: "Rare Holo",
  image: null, variants: ["holofoil"], price: 1000, language: "en", edition_note: null, owned_qty: 0, owned: [] };
const initial = { condition: "NM", language: "en", acquired: null };

describe("AddSheet slab form", () => {
  it("prefills what the label read and sends a grading instead of a condition", async () => {
    const onAdd = vi.fn();
    renderPage(<AddSheet card={card} initial={initial} onBack={() => {}} onAdd={onAdd}
      slab={{ grader: "PSA", grade: 9, cert: "56941091", grader_seen: false }} />);
    const psa = screen.getAllByRole("radio").find((r) => r.textContent === "PSA");
    expect(psa).toHaveAttribute("aria-checked", "true");
    expect(screen.getByLabelText("Grade")).toHaveValue("9");
    expect(screen.getByLabelText("Cert number")).toHaveValue("56941091");
    expect(screen.getByText(/guess from the label layout/)).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "Condition" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Add slab to collection" }));
    const body = onAdd.mock.calls[0][0];
    expect(body.grading).toEqual({ company: "PSA", grade: 9, cert_number: "56941091" });
    expect(body.condition).toBeUndefined();
    expect(body.quantity).toBe(1);
  });

  it("shows an Open <grader> report link when the cert page is known", () => {
    renderPage(<AddSheet card={card} initial={initial} onBack={() => {}} onAdd={vi.fn()} reportUrl="https://acegrading.com/cert/158690"
      slab={{ grader: "ACE", grade: 10, cert: "158690" }} />);
    expect(screen.getByRole("link", { name: "Open ACE report" })).toHaveAttribute("href", "https://acegrading.com/cert/158690");
  });

  it("Other slab: the grader name is required and sent", async () => {
    const onAdd = vi.fn();
    renderPage(<AddSheet card={card} initial={initial} onBack={() => {}} onAdd={onAdd} slab={{ grader: null, grade: null, cert: null }} />);
    expect(screen.getByText(/could not be read/)).toBeInTheDocument();
    const add = screen.getByRole("button", { name: "Add slab to collection" });
    await userEvent.click(screen.getByRole("radio", { name: "Other" }));
    await userEvent.type(screen.getByLabelText("Grade"), "9.5");
    expect(add).toBeDisabled(); // no grader name yet
    await userEvent.type(screen.getByLabelText("Grader name"), "TAG");
    expect(add).toBeEnabled();
    await userEvent.click(add);
    expect(onAdd.mock.calls[0][0].grading).toEqual({ company: "OTHER", grade: 9.5, cert_number: null, grader_name: "TAG" });
  });

  it("rejects a grade that is not 1-10 in half steps", async () => {
    renderPage(<AddSheet card={card} initial={initial} onBack={() => {}} onAdd={() => {}} slab={{ grader: "BGS", grade: null, cert: null }} />);
    await userEvent.type(screen.getByLabelText("Grade"), "9.3");
    expect(screen.getByText(/half steps/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add slab to collection" })).toBeDisabled();
  });

  it("a plain raw scan is unchanged: condition, no slab form", () => {
    renderPage(<AddSheet card={card} initial={initial} onBack={() => {}} onAdd={() => {}} />);
    expect(screen.getByRole("radiogroup", { name: "Condition" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Cert number")).toBeNull();
  });
});
