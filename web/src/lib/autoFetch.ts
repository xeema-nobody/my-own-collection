import { api, ApiError } from "./api";

export type AutoFetch = "started" | "queued" | "offline" | "error";

export const RETRY_MS = 10_000;
const pending = new Set<string>();
let timer: ReturnType<typeof setTimeout> | undefined;

async function drain() {
  timer = undefined;
  const id = pending.values().next().value as string | undefined;
  if (id === undefined) return;
  try {
    await api.fetchCardPrices(id);
    pending.delete(id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) { /* a fetch job is still running: keep it queued */ }
    else if (e instanceof ApiError && e.status === 503) pending.clear();  // fetcher gone: the "needs price" banner covers it
    else pending.delete(id);
  }
  if (pending.size) timer = setTimeout(drain, RETRY_MS);
}

/** Best-effort price fetch for a card that was just added. Never throws. 409 (one job per type) is
 *  retried every RETRY_MS while the page is open; the queue is in memory only. */
export async function requestPriceFetch(cardId: string): Promise<AutoFetch> {
  try {
    await api.fetchCardPrices(cardId);
    return "started";
  } catch (e) {
    if (e instanceof ApiError && e.status === 503) return "offline";
    if (e instanceof ApiError && e.status === 409) {
      pending.add(cardId);
      timer ??= setTimeout(drain, RETRY_MS);
      return "queued";
    }
    return "error";
  }
}

export const queuedCount = () => pending.size;
export function resetAutoFetch() { pending.clear(); if (timer) clearTimeout(timer); timer = undefined; }
