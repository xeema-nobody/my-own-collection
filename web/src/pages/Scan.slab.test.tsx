import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mockApi, renderPage } from "../test/utils";
import Scan from "./Scan";

vi.mock("../lib/scan", async (orig) => ({ ...(await orig<typeof import("../lib/scan")>()), resizePhoto: vi.fn(async (b: Blob) => b) }));

const card = (o: object = {}) => ({
  id: "pokemon:pgo-11", name: "Radiant Charizard", number: "11", printed_total: 78, set: { id: "pgo", name: "Pokémon GO" }, year: 2022,
  rarity: "Radiant Rare", image: "https://img/11.png", variants: ["holofoil"], price: 1500, language: "en", edition_note: null, owned_qty: 0, owned: [], ...o });
const info = (o: object = {}) => ({ grader: "ACE", cert: "158690", status: "found", url: "https://ace/158690", name: "Radiant Charizard", number: "011", printed_total: 78,
  set_name: "Pokemon GO", year: 2022, variant: "Holo", grade: 10, tier: "GEM MINT", ...o });
const cert = (o: object = {}) => ({ cert: info(), cards: [card()], how_exact: "exact", needs_confirm: true, cached: false, report_url: "https://ace/158690", warnings: [], ...o });
const ident = (c: object | null, slab: object = { grader: "ACE", grade: 10, cert: "158690", tier: "GEM MINT", grader_seen: true }) =>
  ({ text: "", confidence: "none", names: [], total: (c as { cards: unknown[] } | null)?.cards.length ?? 0, cards: (c as { cards: unknown[] } | null)?.cards ?? [], slab, cert: c });
const ADD = { "POST /api/scan/add": { label: "Radiant Charizard, Pokémon GO", stack: { id: "s1", quantity: 1 }, event: {} } };

const certUrl = (api: ReturnType<typeof mockApi>) => String(api.mock.calls.find(([u]) => String(u).includes("/api/scan/cert"))![0]);

async function scanSlab() {
  localStorage.setItem("scan.mode", "slab");
  const user = userEvent.setup();
  renderPage(<Scan />, "/scan");
  await user.upload(screen.getByLabelText("Take a photo of the card"), new File(["x"], "c.jpg", { type: "image/jpeg" }));
  return user;
}

describe("Scan page, slab result card", () => {
  beforeEach(() => localStorage.clear());

  it("unsure cert: not looked up, says so and keeps the digits to correct", async () => {
    const api = mockApi({ "POST /api/scan/identify": ident(null, { grader: "PSA", grade: 9, cert: "5694109", tier: "MINT", grader_seen: true, cert_sure: false }) });
    await scanSlab();
    expect(await screen.findByText(/The cert read \(5694109\) has 7 digits, not what PSA prints, so it was not looked up/)).toBeInTheDocument();
    expect(screen.getByLabelText("Cert number")).toHaveValue("5694109");
    expect(api.mock.calls.some(([u]) => String(u).includes("/api/scan/cert"))).toBe(false);
  });

  it("found: shows the page summary, the exact card, and prefills the slab form; adds only on the last tap", async () => {
    const api = mockApi({ "POST /api/scan/identify": ident(cert()), ...ADD });
    const user = await scanSlab();
    expect(await screen.findByText("ACE 10 Gem Mint - Radiant Charizard 011/078 - Pokemon GO 2022 - Holo - cert 158690")).toBeInTheDocument();
    expect(screen.getByText(/Matches the page/)).toBeInTheDocument();
    expect(screen.queryByText(/Name read clearly/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open ACE report/ })).toHaveAttribute("href", "https://ace/158690");
    expect(api.mock.calls.some(([u]) => String(u).endsWith("/api/scan/add"))).toBe(false);
    await user.click(screen.getByRole("button", { name: /Radiant Charizard, Pokémon GO 11/ }));
    expect(screen.getByRole("radio", { name: "ACE" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByLabelText("Grade")).toHaveValue("10");
    expect(screen.getByLabelText("Cert number")).toHaveValue("158690");
    await user.click(screen.getByRole("button", { name: /Add slab to collection/ }));
    await screen.findByText(/Added: Radiant Charizard/);
    const body = JSON.parse((api.mock.calls.find(([u]) => String(u).endsWith("/api/scan/add"))![1] as RequestInit).body as string);
    expect(body).toMatchObject({ card_id: "pokemon:pgo-11", grading: { company: "ACE", grade: 10, cert_number: "158690" } });
  });

  it("label unreadable on the grade: the grade comes from the page", async () => {
    mockApi({ "POST /api/scan/identify": ident(cert(), { grader: "ACE", grade: null, cert: "158690", grader_seen: true }) });
    const user = await scanSlab();
    await user.click(await screen.findByRole("button", { name: /Radiant Charizard, Pokémon GO 11/ }));
    expect(screen.getByLabelText("Grade")).toHaveValue("10");
  });

  it("not found: says so and offers no card", async () => {
    mockApi({ "POST /api/scan/identify": ident(cert({ cert: info({ status: "not_found", name: null, number: null }), cards: [], how_exact: "none", needs_confirm: false, report_url: null })) });
    await scanSlab();
    expect(await screen.findByText(/ACE has no record of cert 158690/)).toBeInTheDocument();
    expect(screen.queryByText("Most likely")).not.toBeInTheDocument();
    expect(screen.getByText(/No card from the catalog yet/)).toBeInTheDocument();
  });

  it("disagreement: shows 'label says X / page says Y: check the cert digits', and fixing the cert looks up again", async () => {
    const api = mockApi({
      "POST /api/scan/identify": ident(cert({ warnings: [{ code: "grade_mismatch", text: "label says 9, page says 10" }] }), { grader: "ACE", grade: 9, cert: "158690", grader_seen: true }),
      "GET /api/scan/cert": cert({ cert: info({ cert: "158691", grade: 9, name: "Pikachu" }), cards: [card({ id: "pokemon:x-1", name: "Pikachu", number: "1" })], warnings: [] }),
    });
    const user = await scanSlab();
    expect(await screen.findByText("label says 9, page says 10: check the cert digits.")).toBeInTheDocument();
    const field = screen.getByLabelText("Cert number");
    await user.clear(field);
    await user.type(field, "158 691");
    await user.click(screen.getByRole("button", { name: "Look up again" }));
    expect(await screen.findByRole("button", { name: /Pikachu, Pokémon GO 1/ })).toBeInTheDocument();
    expect(certUrl(api)).toContain("grader=ACE");
    expect(certUrl(api)).toContain("cert=158691");
    expect(certUrl(api)).toContain("grade=9");
    await waitFor(() => expect(screen.queryByText(/check the cert digits/)).not.toBeInTheDocument());
  });

  it("a different grader can be picked and looked up", async () => {
    const api = mockApi({ "POST /api/scan/identify": ident(null, { grader: null, grade: null, cert: null }), "GET /api/scan/cert": cert({ cert: info({ grader: "PSA" }) }) });
    const user = await scanSlab();
    expect(await screen.findByText(/The label could not be read/)).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "PSA" }));
    await user.type(screen.getByLabelText("Cert number"), "146737388");
    await user.click(screen.getByRole("button", { name: "Look up" }));
    expect(await screen.findByText(/PSA 10 Gem Mint - Radiant Charizard/)).toBeInTheDocument();
    expect(certUrl(api)).toContain("grader=PSA");
  });

  it("link-only grader: report link and typing, no card", async () => {
    mockApi({ "POST /api/scan/identify": ident(cert({ cert: info({ grader: "CGC", status: "link_only", name: null, number: null }), cards: [], how_exact: "none", needs_confirm: false, report_url: "https://cgc/158690" }), { grader: "CGC", grade: 9, cert: "158690", grader_seen: true }) });
    await scanSlab();
    expect(await screen.findByText(/CGC has no page this app can read/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open CGC report/ })).toHaveAttribute("href", "https://cgc/158690");
  });

  it("found but not in the catalog (Japanese): shows the cert details and a name search prefilled with the page name", async () => {
    mockApi({ "POST /api/scan/identify": ident(cert({ cert: info({ name: "Pikachu", number: "25", language: "Japanese" }), cards: [], how_exact: "none", needs_confirm: false })) });
    await scanSlab();
    expect(await screen.findByText(/This card is not in the catalog/)).toBeInTheDocument();
    expect(screen.getByText(/ACE 10 Gem Mint - Pikachu 25/)).toBeInTheDocument();
    expect(screen.getByLabelText("Type the card name")).toHaveValue("Pikachu");
  });

  it("non-Pokemon page: warns that the cert was probably misread", async () => {
    mockApi({ "POST /api/scan/identify": ident(cert({ cert: info({ grader: "PSA", name: "HANK AARON", number: null, set_name: "1976 O-Pee-Chee", variant: null }), cards: [], how_exact: "none", needs_confirm: false,
      warnings: [{ code: "not_pokemon", text: "the page is not a Pokemon card (HANK AARON, 1976 O-Pee-Chee)" }] }), { grader: "PSA", grade: 9, cert: "2023151", grader_seen: true }) });
    await scanSlab();
    expect(await screen.findByText(/the page is not a Pokemon card \(HANK AARON.*check the cert digits/)).toBeInTheDocument();
  });

  it("raw mode is untouched: no slab result card", async () => {
    mockApi({ "POST /api/scan/identify": { text: "x", confidence: "high", names: ["x"], total: 1, cards: [card()] } });
    const user = userEvent.setup();
    renderPage(<Scan />, "/scan");
    await user.upload(screen.getByLabelText("Take a photo of the card"), new File(["x"], "c.jpg", { type: "image/jpeg" }));
    await screen.findByText(/Tap the one you hold/);
    expect(screen.queryByRole("region", { name: "Slab result" })).not.toBeInTheDocument();
  });
});
