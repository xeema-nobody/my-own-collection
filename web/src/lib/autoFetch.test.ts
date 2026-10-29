import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";
import { queuedCount, requestPriceFetch, resetAutoFetch, RETRY_MS } from "./autoFetch";

const ok = { started: true, cards: 1 };

describe("requestPriceFetch", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => { resetAutoFetch(); vi.useRealTimers(); vi.restoreAllMocks(); });

  it("starts a fetch", async () => {
    const spy = vi.spyOn(api, "fetchCardPrices").mockResolvedValue(ok);
    expect(await requestPriceFetch("pokemon:a-1")).toBe("started");
    expect(spy).toHaveBeenCalledWith("pokemon:a-1");
  });

  it("reports an offline fetcher (503) and queues nothing", async () => {
    vi.spyOn(api, "fetchCardPrices").mockRejectedValue(new ApiError("down", 503));
    expect(await requestPriceFetch("pokemon:a-1")).toBe("offline");
    expect(queuedCount()).toBe(0);
  });

  it("queues on 409 and retries until the running job ends", async () => {
    const spy = vi.spyOn(api, "fetchCardPrices")
      .mockRejectedValueOnce(new ApiError("running", 409))
      .mockRejectedValueOnce(new ApiError("running", 409))
      .mockResolvedValue(ok);
    expect(await requestPriceFetch("pokemon:a-1")).toBe("queued");
    expect(queuedCount()).toBe(1);
    await vi.advanceTimersByTimeAsync(RETRY_MS);   // still 409
    expect(queuedCount()).toBe(1);
    await vi.advanceTimersByTimeAsync(RETRY_MS);   // job ended
    expect(queuedCount()).toBe(0);
    expect(spy).toHaveBeenCalledTimes(3);
  });

  it("never throws on other errors", async () => {
    vi.spyOn(api, "fetchCardPrices").mockRejectedValue(new Error("boom"));
    expect(await requestPriceFetch("pokemon:a-1")).toBe("error");
  });
});
