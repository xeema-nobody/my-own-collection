import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import Scan from "./Scan";

vi.mock("../lib/scan", async (orig) => ({ ...(await orig<typeof import("../lib/scan")>()), resizePhoto: vi.fn(async (b: Blob) => b) }));

const card = { id: "pokemon:base1-4", name: "Charizard", number: "4", printed_total: 102, set: { id: "base1", name: "Base" }, year: 1999,
  rarity: "Rare Holo", image: "https://img/4.png", variants: ["holofoil"], price: 41846, language: "en", edition_note: null, owned_qty: 0, owned: [] };
const IDENT = { text: "Charizard", confidence: "high", names: ["charizard"], total: 1, cards: [card] };
const ADDED = { label: "Charizard, Base", stack: { id: "s1", quantity: 1 }, event: { id: "e1", grading: null } };
const routes = () => ({ "POST /api/scan/identify": IDENT, "POST /api/scan/add": ADDED, "POST /api/scan/photo": { id: "p1" } });
const photoCalls = (api: ReturnType<typeof mockApi>) => api.mock.calls.filter(([u]) => String(u).includes("/api/scan/photo"));

async function toDetails() {
  const user = userEvent.setup();
  renderPage(<Scan />, "/scan");
  await user.upload(screen.getByLabelText("Take a photo of the card"), new File(["x"], "c.jpg", { type: "image/jpeg" }));
  await user.click(await screen.findByRole("button", { name: /Charizard, Base 4/ }));
  return user;
}

describe("Scan photo saving", () => {
  beforeEach(() => localStorage.clear());

  it("keeps the scan photo with the added stack by default", async () => {
    const api = mockApi(routes());
    const user = await toDetails();
    expect(screen.getByRole("switch", { name: "Save photo" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: /Add 1 to collection/ }));
    expect(await screen.findByText(/Added: Charizard, Base/)).toBeInTheDocument();
    await waitFor(() => expect(photoCalls(api)).toHaveLength(1));
    const url = String(photoCalls(api)[0][0]);
    expect(url).toContain("stack_id=s1");
    expect(url).toContain("kind=front");
  });

  it("does not upload when the switch is off, and remembers that", async () => {
    const api = mockApi(routes());
    const user = await toDetails();
    await user.click(screen.getByRole("switch", { name: "Save photo" }));
    await user.click(screen.getByRole("button", { name: /Add 1 to collection/ }));
    expect(await screen.findByText(/Added: Charizard, Base/)).toBeInTheDocument();
    expect(photoCalls(api)).toHaveLength(0);
    expect(localStorage.getItem("scan.savePhoto")).toBe("0");
  });

  it("offers more photos after the add and uploads the back shot", async () => {
    const api = mockApi(routes());
    const user = await toDetails();
    await user.click(screen.getByRole("button", { name: /Add 1 to collection/ }));
    await user.click(await screen.findByRole("button", { name: /Add more photos/ }));
    expect(screen.getByText("Back of the card")).toBeInTheDocument();
    await user.upload(screen.getByLabelText("Take a photo of the card"), new File(["y"], "b.jpg", { type: "image/jpeg" }));
    await waitFor(() => expect(photoCalls(api).some(([u]) => String(u).includes("kind=back"))).toBe(true));
    expect(await screen.findByText("A corner close-up")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Done with photos" }));
    expect(await screen.findByText(/Added: Charizard, Base/)).toBeInTheDocument();
  });
});
