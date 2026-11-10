import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import Scan from "./Scan";

vi.mock("../lib/scan", async (orig) => ({ ...(await orig<typeof import("../lib/scan")>()), resizePhoto: vi.fn(async (b: Blob) => b) }));

const S9 = { id: "S9", name: "スターバース", total: 127, printed_total: 100, imported: 0, reason: "set code, printed total" };
const jaCard = { id: "pokemon-ja:S9-103", name: "Charizard V", number: "103", printed_total: 100, set: { id: "S9", name: "スターバース" }, year: 2021, rarity: "SR",
  image: null, variants: [], price: null, language: "ja", edition_note: null, owned_qty: 0, owned: [] };
const none = { text: "", confidence: "none", names: [], total: 0, cards: [], read: { number: "103", printed_total: 100, set_code: "s9", hp: 220 } };
const found = { ...none, confidence: "high", total: 1, cards: [jaCard] };

const calls = (api: ReturnType<typeof mockApi>, path: string) => api.mock.calls.filter(([u]) => String(u).includes(path));

async function scanPhoto() {
  const user = userEvent.setup();
  renderPage(<Scan />, "/scan");
  await user.upload(screen.getByLabelText("Take a photo of the card"), new File(["x"], "c.jpg", { type: "image/jpeg" }));
  return user;
}

describe("Scan page, import a Japanese set on demand", () => {
  beforeEach(() => localStorage.clear());

  it("no match: suggests the set, one confirm imports it, shows progress, then matches again", async () => {
    let n = 0;
    const api = mockApi({
      "POST /api/scan/identify": () => (n++ === 0 ? none : found),
      "GET /api/scan/ja/suggest": { sets: [S9] },
      "POST /api/scan/ja/import": { started: true, set: "S9" },
      "GET /api/scan/ja/import": { state: "done", set: "S9", done: 127, expected: 127, failed: [] },
    });
    const user = await scanPhoto();
    await user.click(await screen.findByRole("radio", { name: /S9/ }));
    await user.click(screen.getByRole("button", { name: /Import S9 \(127 cards, catalog only\)/ }));
    expect(await screen.findByText("Charizard V")).toBeInTheDocument();      // the match ran again
    expect(String(calls(api, "/api/scan/ja/suggest")[0][0])).toContain("code=s9");
    expect(calls(api, "/api/scan/ja/import").some(([u, i]) => (i as RequestInit | undefined)?.method === "POST" && String(u).includes("set=S9"))).toBe(true);
    expect(calls(api, "/api/scan/identify")).toHaveLength(2);
    expect(calls(api, "/api/scan/add")).toHaveLength(0);                     // nothing is ever added by the import
    expect(calls(api, "/api/collection")).toHaveLength(0);
  });

  it("still no card after the import: says the set is imported but the card is not in it", async () => {
    mockApi({
      "POST /api/scan/identify": none,
      "GET /api/scan/ja/suggest": { sets: [S9] },
      "POST /api/scan/ja/import": { started: true, set: "S9" },
      "GET /api/scan/ja/import": { state: "done", set: "S9", done: 127, expected: 127, failed: [] },
    });
    const user = await scanPhoto();
    await user.click(await screen.findByRole("radio", { name: /S9/ }));
    await user.click(screen.getByRole("button", { name: /Import S9/ }));
    expect(await screen.findByText(/Set S9 is imported, but this card is not in it/)).toBeInTheDocument();
  });

  it("a failed import is reported and can be retried", async () => {
    mockApi({
      "POST /api/scan/identify": none,
      "GET /api/scan/ja/suggest": { sets: [S9] },
      "POST /api/scan/ja/import": { status: 409, body: { detail: "catalog_import already running" } },
    });
    const user = await scanPhoto();
    await user.click(await screen.findByRole("radio", { name: /S9/ }));
    await user.click(screen.getByRole("button", { name: /Import S9/ }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Import S9/ })).toBeEnabled();
  });

  it("no prompt when the photo matched", async () => {
    mockApi({ "POST /api/scan/identify": found });
    await scanPhoto();
    expect(await screen.findByText("Charizard V")).toBeInTheDocument();
    expect(screen.queryByLabelText("Japanese set import")).toBeNull();
  });
});
