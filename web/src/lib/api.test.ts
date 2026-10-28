import { afterEach, describe, expect, it, vi } from "vitest";
import { ago, api, ApiError, money } from "./api";

const reply = (status: number, body?: unknown) =>
  vi.stubGlobal("fetch", vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status })));
const lastUrl = () => String((fetch as any).mock.calls.at(-1)[0]);

afterEach(() => vi.unstubAllGlobals());

describe("query string building", () => {
  it("drops empty values and repeats arrays", async () => {
    reply(200, []);
    await api.cards({ q: "char", set: "", page: undefined, type: ["fire", "water"], n: 0 });
    expect(lastUrl()).toMatch(/\/api\/cards\?q=char&type=fire&type=water&n=0$/);
  });
  it("no params -> no question mark", async () => {
    reply(200, []);
    await api.cards({});
    expect(lastUrl()).toMatch(/\/api\/cards$/);
  });
});

describe("req errors", () => {
  it("string detail becomes ApiError message", async () => {
    reply(404, { detail: "Card not found" });
    await expect(api.card("x")).rejects.toMatchObject({ message: "Card not found", status: 404 });
  });
  it("structured detail is JSON-stringified", async () => {
    reply(422, { detail: [{ msg: "bad" }] });
    await expect(api.card("x")).rejects.toThrow('[{"msg":"bad"}]');
  });
  it("non-JSON body falls back to status text", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 500, statusText: "Server Error" })));
    const e = await api.card("x").catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect(e.status).toBe(500);
  });
  it("204 resolves undefined", async () => {
    reply(204);
    await expect(api.deleteItem("1")).resolves.toBeUndefined();
  });
});

describe("importCollection", () => {
  const file = new File(["{}"], "c.json");
  it("returns the summary and posts the raw file", async () => {
    reply(200, { created: 1, updated: 2, errors: [] });
    await expect(api.importCollection(file, "json", "add")).resolves.toEqual({ created: 1, updated: 2, errors: [] });
    expect(lastUrl()).toMatch(/import\?format=json&mode=add$/);
    expect((fetch as any).mock.calls[0][1].body).toBe(file);
  });
  it("throws ApiError on failure", async () => {
    reply(413, { detail: "too big" });
    await expect(api.importCollection(file, "csv", "set")).rejects.toMatchObject({ message: "too big", status: 413 });
  });
});

describe("formatters", () => {
  it("money: null -> dash, cents -> currency", () => {
    expect(money(null)).toBe("—");
    expect(money(undefined)).toBe("—");
    expect(money(0)).toMatch(/0[.,]00/);
    expect(money(12345)).toMatch(/123[.,]45/);
  });
  it("ago buckets", () => {
    const iso = (s: number) => new Date(Date.now() - s * 1000).toISOString();
    expect(ago(null)).toBe("never");
    expect(ago(iso(10))).toBe("just now");
    expect(ago(iso(600))).toBe("10 min ago");
    expect(ago(iso(7200))).toBe("2 h ago");
    expect(ago(iso(3 * 86400))).toBe("3 d ago");
  });
  it("ago treats naive timestamps as UTC", () => {
    const naive = new Date(Date.now() - 600_000).toISOString().replace("Z", "");
    expect(ago(naive)).toBe("10 min ago");
  });
});
