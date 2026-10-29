import { describe, expect, it } from "vitest";
import { durationSec, fmtDuration, jobLabel, jobSummary } from "./jobs";

describe("jobs helpers", () => {
  it("labels known and unknown types", () => {
    expect(jobLabel("price_fetch")).toBe("Price fetch");
    expect(jobLabel("some_new_job")).toBe("some new job");
  });
  it("duration treats naive stamps as UTC", () => {
    expect(durationSec("2026-10-28T10:00:00", "2026-10-28T10:01:30")).toBe(90);
    expect(durationSec(null)).toBeNull();
    expect(fmtDuration(90)).toBe("1m 30s");
    expect(fmtDuration(7260)).toBe("2h 1m");
  });
  it("summarises stats and falls back to error", () => {
    expect(jobSummary({ type: "price_refresh", status: "ok", stats: { cards: 5, prices: 20, errors: 0 } })).toBe("5 cards, 20 prices");
    expect(jobSummary({ type: "snapshot", status: "ok", stats: {}, error: "boom" })).toBe("boom");
    expect(jobSummary({ type: "snapshot", status: "running", stats: {} })).toBe("starting…");
  });
});
