export const JOB_LABEL: Record<string, string> = {
  catalog_import: "Catalog import", price_refresh: "Price refresh", price_fetch: "Price fetch", snapshot: "Snapshot", alerts: "Alert check",
};
export const jobLabel = (t: string) => JOB_LABEL[t] ?? t.replace(/_/g, " ");

export function jobTone(status: string): "ok" | "warn" | "danger" | "accent" | "neutral" {
  return ({ ok: "ok", running: "accent", partial: "warn", skipped: "neutral", interrupted: "warn", failed: "danger", error: "danger" } as const)[status as "ok"] ?? "neutral";
}

/** Seconds between two ISO stamps (end defaults to now); null when start is missing. */
export function durationSec(start?: string | null, end?: string | null, now = Date.now()): number | null {
  if (!start) return null;
  const s = Date.parse(start.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(start) ? start : start + "Z");
  const e = end ? Date.parse(end.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(end) ? end : end + "Z") : now;
  return Number.isNaN(s) || Number.isNaN(e) ? null : Math.max(Math.round((e - s) / 1000), 0);
}

export function fmtDuration(sec: number | null): string {
  if (sec == null) return "";
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${sec % 60}s`;
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
}

/** One-line human summary of `job.stats`. */
export function jobSummary(j: { type: string; status: string; stats?: any; error?: string | null }): string {
  const s = j.stats ?? {};
  const parts: string[] = [];
  const add = (n: unknown, text: string) => { if (typeof n === "number" && n > 0) parts.push(`${n} ${text}`); };
  if (j.type === "price_fetch") {
    if (s.total != null) parts.push(`${s.done ?? 0}/${s.total} cards`);
    add(s.ok, "ok"); add(s.failed, "failed"); add(s.needs_match, "need a match"); add(s.not_found, "not found");
    add(s.skipped_cached, "cached"); add(s.sales_new, "new sales");
  } else if (j.type === "catalog_import") {
    if (s.set) parts.push(`set ${s.set}`);
    add(s.sets, "sets"); add(s.cards, "cards"); add(s.prices, "prices");
    add(s.failed_sets?.length, "sets failed"); add(s.incomplete_sets?.length, "incomplete");
  } else if (j.type === "price_refresh") {
    add(s.cards, "cards"); add(s.prices, "prices"); add(s.errors, "errors");
  } else {
    Object.entries(s).filter(([, v]) => typeof v === "number" || typeof v === "string").slice(0, 4).forEach(([k, v]) => parts.push(`${k} ${v}`));
  }
  if (!parts.length && j.error) return j.error;
  return parts.join(", ") || (j.status === "running" ? "starting…" : "no details");
}
