import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../../test/utils";
import AddSealed from "./AddSealed";

const SETS = [{ external_id: "sv3", name: "Obsidian Flames" }, { external_id: "sv1", name: "Scarlet & Violet" }];
const TYPES = [{ value: "booster_box", label: "Booster Box" }, { value: "etb", label: "Elite Trainer Box" }];

describe("AddSealed", () => {
  it("picks the set from the list and posts the product", async () => {
    let body: any = null;
    mockApi({ "/api/sets": SETS, "/api/sealed/types": TYPES,
      "POST /api/sealed": (init?: RequestInit) => { body = JSON.parse(String(init?.body)); return { id: "s1", entry: { name: "x" } }; } });
    renderPage(<AddSealed open onClose={() => {}} />);
    await userEvent.click(await screen.findByRole("combobox", { name: "Set" }).catch(() => screen.getByLabelText("Set")));
    await userEvent.click(await screen.findByText("Obsidian Flames (sv3)"));
    await userEvent.type(screen.getByLabelText("Edition"), "Costco");
    await userEvent.click(screen.getByRole("button", { name: "Add to collection" }));
    await waitFor(() => expect(body).toMatchObject({ set_id: "sv3", type: "booster_box", language: "en", edition: "Costco", quantity: 1 }));
  });
  it("needs a set: no request without one", async () => {
    const f = mockApi({ "/api/sets": SETS, "/api/sealed/types": TYPES });
    renderPage(<AddSealed open onClose={() => {}} />);
    await userEvent.click(await screen.findByRole("button", { name: "Add to collection" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Pick a set");
    expect(f.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toBe(false);
  });
});
