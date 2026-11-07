import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import Scan from "./Scan";

vi.mock("../lib/scan", async (orig) => ({ ...(await orig<typeof import("../lib/scan")>()), resizePhoto: vi.fn(async (b: Blob) => b) }));

const card = (o: object = {}) => ({
  id: "pokemon:base1-4", name: "Charizard", number: "4", printed_total: 102, set: { id: "base1", name: "Base" }, year: 1999,
  rarity: "Rare Holo", image: "https://img/4.png", variants: ["holofoil"], price: 41846, language: "en",
  edition_note: "1st Edition / Shadowless / Unlimited", owned_qty: 0, owned: [], ...o });
const base2 = card({ id: "pokemon:base2-99", name: "Charizard", number: "99", set: { id: "base2", name: "Jungle" }, year: 1999, edition_note: null, price: null });
const IDENT = { text: "Charizard", confidence: "high", names: ["charizard"], total: 2, cards: [card(), base2] };

async function scanPhoto() {
  const user = userEvent.setup();
  renderPage(<Scan />, "/scan");
  await user.upload(screen.getByLabelText("Take a photo of the card"), new File(["x"], "c.jpg", { type: "image/jpeg" }));
  return user;
}

describe("Scan page", () => {
  beforeEach(() => localStorage.clear());

  it("without a camera API it offers the phone's own camera, and never adds before the last tap", async () => {
    const api = mockApi({ "POST /api/scan/identify": IDENT, "POST /api/scan/add": { label: "Charizard, Base", stack: { id: "s1", quantity: 1 }, event: {} } });
    const user = await scanPhoto();
    expect(await screen.findByText(/Tap the one you hold/)).toBeInTheDocument();
    // both versions are shown with their markers; the first is "Most likely"
    expect(screen.getByText("Most likely")).toBeInTheDocument();
    expect(screen.getByText(/Also exists as 1st Edition \/ Shadowless/)).toBeInTheDocument();
    expect(screen.getByText("Jungle", { exact: false })).toBeInTheDocument();
    expect(api.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === "POST" && String(api.mock.calls[0][0]).includes("/add"))).toBe(false);

    await user.click(screen.getByRole("button", { name: /Charizard, Base 4/ }));
    await user.click(screen.getByRole("radio", { name: "LP" }));
    await user.click(screen.getByRole("button", { name: /Add 1 to collection/ }));
    expect(await screen.findByText(/Added: Charizard, Base/)).toBeInTheDocument();
    const add = api.mock.calls.find(([u]) => String(u).endsWith("/api/scan/add"))!;
    expect(JSON.parse((add[1] as RequestInit).body as string)).toMatchObject({ card_id: "pokemon:base1-4", condition: "LP", variant: "holofoil", quantity: 1, language: "en" });
    expect(JSON.parse(localStorage.getItem("scan.choice")!).condition).toBe("LP"); // remembered for the next card
  });

  it("shows what was read and which signals agree, and drops 'Most likely' when the top prints tie", async () => {
    const tied = { ...IDENT, read: { number: "4", printed_total: 102, set_code: null, hp: 120 },
      cards: [{ ...card(), signals: ["name", "number", "total"], match_label: "name + number + printed total match" },
              { ...base2, signals: ["name", "number", "total"], match_label: "name + number + printed total match" }] };
    mockApi({ "POST /api/scan/identify": tied });
    await scanPhoto();
    expect(await screen.findByText("Read #4/102")).toBeInTheDocument();
    expect(screen.getAllByText("name + number + printed total")).toHaveLength(2);
    expect(screen.queryByText("Most likely")).not.toBeInTheDocument();
  });

  it("shows when the copy joins an existing stack", async () => {
    mockApi({ "POST /api/scan/identify": { ...IDENT, cards: [card({ owned_qty: 2, owned: [{ condition: "NM", language: "en", variant: "holofoil", grading: null, quantity: 2 }] })] } });
    const user = await scanPhoto();
    await user.click(await screen.findByRole("button", { name: /Charizard, Base 4/ }));
    expect(screen.getByText(/You already own 2 in this condition.*3 total/)).toBeInTheDocument();
  });

  it("says plainly when the computer cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await scanPhoto();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Can't reach your computer.*Tailscale/);
  });

  it("an unreadable card falls back to typing the name", async () => {
    const api = mockApi({ "POST /api/scan/identify": { text: "", confidence: "none", names: [], total: 0, cards: [] },
      "GET /api/scan/search": { total: 1, page: 1, cards: [card()] } });
    const user = await scanPhoto();
    expect(await screen.findByText(/Couldn't read a card name/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Type the card name"), "charizard");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText(/Tap the one you hold/)).toBeInTheDocument();
    await waitFor(() => expect(api.mock.calls.some(([u]) => String(u).includes("q=charizard"))).toBe(true));
  });

  it("batch mode returns to the camera, counts, and undoes the last add", async () => {
    let n = 0;
    const api = mockApi({
      "POST /api/scan/identify": IDENT,
      "POST /api/scan/add": () => ({ label: "Charizard, Base", stack: { id: "s1", quantity: ++n }, event: { id: `e${n}` } }),
      "POST /api/scan/undo": { label: "Charizard, Base", quantity: 0, deleted: true, event_id: "u1" },
    });
    const user = userEvent.setup();
    renderPage(<Scan />, "/scan");
    await user.click(screen.getByRole("switch", { name: "Batch mode" }));
    await user.upload(screen.getByLabelText("Take a photo of the card"), new File(["x"], "c.jpg", { type: "image/jpeg" }));
    await user.click(await screen.findByRole("button", { name: /Charizard, Base 4/ }));
    await user.click(screen.getByRole("button", { name: /Add 1 to collection/ }));
    expect(await screen.findByText(/1 added/)).toBeInTheDocument();
    expect(screen.getByLabelText("Take a photo of the card")).toBeInTheDocument(); // camera ready again
    await user.click(screen.getByRole("button", { name: /Undo last/ }));
    await waitFor(() => expect(screen.queryByText(/1 added/)).toBeNull());
    expect(JSON.parse((api.mock.calls.find(([u]) => String(u).endsWith("/api/scan/undo"))![1] as RequestInit).body as string)).toEqual({ event_id: "e1" });
  });

  it("typed number + set finds the print", async () => {
    const api = mockApi({ "GET /api/scan/lookup": { ...IDENT, total: 1, cards: [card()], exact: true } });
    const user = userEvent.setup();
    renderPage(<Scan />, "/scan");
    await user.type(screen.getByLabelText("Card number"), "4/102");
    await user.type(screen.getByLabelText("Set code or name"), "base");
    await user.click(screen.getByRole("button", { name: "Find" }));
    expect(await screen.findByRole("button", { name: /Charizard, Base 4/ })).toBeInTheDocument();
    expect(String(api.mock.calls.find(([u]) => String(u).includes("/api/scan/lookup"))![0])).toContain("number=4%2F102");
  });

  it("shows the link banner when the laptop opened a session", async () => {
    mockApi({ "GET /api/scan/session": { session: { id: "s1", created_at: "" } } });
    renderPage(<Scan />, "/scan");
    expect(await screen.findByText(/Linked to your computer/)).toBeInTheDocument();
  });

  it("scan mode defaults to raw, is remembered, and slab mode sends slab=1", async () => {
    const api = mockApi({ "POST /api/scan/identify": IDENT });
    const user = userEvent.setup();
    renderPage(<Scan />, "/scan");
    expect(screen.getByRole("radio", { name: "Scan raw" })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("radio", { name: "Scan slab" }));
    expect(localStorage.getItem("scan.mode")).toBe("slab");
    await user.upload(screen.getByLabelText("Take a photo of the card"), new File(["x"], "c.jpg", { type: "image/jpeg" }));
    await screen.findByText(/Tap the one you hold/);
    expect(String(api.mock.calls.find(([u]) => String(u).includes("/api/scan/identify"))![0])).toContain("slab=1");
  });

  it("starts in slab mode when that was the remembered choice", () => {
    localStorage.setItem("scan.mode", "slab");
    mockApi({});
    renderPage(<Scan />, "/scan");
    expect(screen.getByRole("radio", { name: "Scan slab" })).toHaveAttribute("aria-checked", "true");
  });

  it("raw scan that found a slab label shows a visible prompt, and its button switches mode and retakes", async () => {
    mockApi({ "POST /api/scan/identify": { ...IDENT, detected: true, slab: { grader: "PSA", grade: 9, cert: "56941091", tier: "MINT", grader_seen: false } } });
    const user = await scanPhoto();
    expect(await screen.findByText(/Looks like a slab/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Switch to slab and retake/ }));
    expect(localStorage.getItem("scan.mode")).toBe("slab");
    expect(await screen.findByRole("radio", { name: "Scan slab" })).toHaveAttribute("aria-checked", "true");
  });

  it("no prompt for a bare raw card", async () => {
    mockApi({ "POST /api/scan/identify": { ...IDENT, detected: false } });
    await scanPhoto();
    await screen.findByText(/Tap the one you hold/);
    expect(screen.queryByText(/Looks like a slab/)).not.toBeInTheDocument();
  });
});
