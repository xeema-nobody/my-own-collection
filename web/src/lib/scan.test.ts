import { beforeEach, describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { CARD_RATIO, fitWidth, friendlyScanError, guideRect, loadChoice, saveChoice } from "./scan";

describe("friendlyScanError", () => {
  it("explains a network failure in plain words", () => {
    expect(friendlyScanError(new TypeError("Failed to fetch"))).toMatch(/Tailscale is on.*computer is awake/);
  });
  it("maps statuses", () => {
    expect(friendlyScanError(new ApiError("x", 403))).toMatch(/refused this phone/);
    expect(friendlyScanError(new ApiError("x", 413))).toMatch(/too big/);
    expect(friendlyScanError(new ApiError("x", 503))).toMatch(/type the card name/);
    expect(friendlyScanError(new ApiError("not a readable image", 422))).toBe("not a readable image");
  });
});

describe("guideRect", () => {
  it("is card shaped and centred in a portrait frame", () => {
    const r = guideRect(1080, 1920);
    expect(r.sw / r.sh).toBeCloseTo(CARD_RATIO, 1);
    expect(r.sx * 2 + r.sw).toBeCloseTo(1080, -1);
    expect(r.sy * 2 + r.sh).toBeCloseTo(1920, -1);
  });
  it("is limited by height in a landscape frame", () => {
    const r = guideRect(1920, 1080);
    expect(r.sh).toBeLessThanOrEqual(1080 * 0.82 + 1);
    expect(r.sw / r.sh).toBeCloseTo(CARD_RATIO, 1);
  });
});

describe("fitWidth", () => {
  it("only shrinks", () => {
    expect(fitWidth(2000, 1000, 1000)).toEqual({ w: 1000, h: 500 });
    expect(fitWidth(500, 400, 1000)).toEqual({ w: 500, h: 400 });
  });
});

describe("remembered choice", () => {
  beforeEach(() => localStorage.clear());
  it("defaults to NM / English", () => expect(loadChoice()).toEqual({ condition: "NM", language: "en", acquired: null }));
  it("round-trips and ignores junk", () => {
    saveChoice({ condition: "LP", language: "ja", acquired: { type: "pulled", price: 0, currency: "EUR" } });
    expect(loadChoice().condition).toBe("LP");
    localStorage.setItem("scan.choice", JSON.stringify({ condition: "XX", language: "en" }));
    expect(loadChoice().condition).toBe("NM");
    localStorage.setItem("scan.choice", "{bad");
    expect(loadChoice().condition).toBe("NM");
  });
});
