import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, FETCHER_START_CMD, type FetchMode, type FetchScope } from "../lib/api";
import { usePriceFetchJob } from "../lib/fetchJob";
import { Button, Input, SegmentedControl } from "./ui";
import FetcherBadge from "./FetcherBadge";
import FetchProgress from "./FetchProgress";

const SCOPES: { value: FetchScope; label: string; noun: string }[] = [
  { value: "collection", label: "Collection", noun: "in the collection" },
  { value: "wishlist", label: "Wishlist", noun: "on the wishlist" },
  { value: "both", label: "Both", noun: "in the collection and on the wishlist (collection first)" },
];

const MODES: { value: Exclude<FetchMode, "stack">; label: string; hint: string }[] = [
  { value: "all", label: "All", hint: "Every card {noun} (cards fetched in the last 24 h are skipped)." },
  { value: "never", label: "Never fetched", hint: "Only cards with no successful fetch yet." },
  { value: "stale", label: "Stale", hint: "Cards never fetched or not refreshed for the chosen number of days." },
  { value: "valuable", label: "Most valuable first", hint: "Every card {noun}, highest value first (so a cancelled run still covers what matters)." },
];

export const fetchErrorText = (e: unknown) =>
  e instanceof ApiError && e.status === 409 ? "A price fetch is already running."
    : e instanceof ApiError && e.status === 503 ? `Fetcher not reachable. Start it on the host: ${FETCHER_START_CMD}`
    : e instanceof ApiError && e.status === 422 ? "Nothing to fetch for that selection."
    : String(e instanceof Error ? e.message : e);

/** "Fetch all prices" with a scope + mode picker; shows live progress of the (server-side) job, also after a reload. */
export default function BulkFetch({ defaultScope = "collection" }: { defaultScope?: FetchScope }) {
  const qc = useQueryClient();
  const [mode, setMode] = useState<Exclude<FetchMode, "stack">>("all");
  const [scope, setScope] = useState<FetchScope>(defaultScope);
  const [days, setDays] = useState(7);
  const { running, latest } = usePriceFetchJob(() => qc.invalidateQueries());
  const go = useMutation({
    mutationFn: () => api.fetchPrices({ mode, scope, ...(mode === "stale" ? { stale_days: days } : {}) }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
  const show = running ?? (latest?.stats?.mode ? latest : undefined);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <Button disabled={!!running || go.isPending} onClick={() => go.mutate()}>Fetch all prices</Button>
        <SegmentedControl label="Cards from" value={scope} onChange={setScope} options={SCOPES.map(({ value, label }) => ({ value, label }))} />
        <SegmentedControl label="Which cards" value={mode} onChange={setMode} options={MODES.map(({ value, label }) => ({ value, label }))} />
        {mode === "stale" && <label className="flex items-center gap-1.5 text-xs text-muted">older than
          <div className="w-16"><Input aria-label="Stale after days" type="number" min={1} max={365} value={days}
            onChange={(e) => setDays(Math.max(1, Math.min(365, Number(e.target.value) || 1)))} /></div> days</label>}
        <FetcherBadge />
      </div>
      <p className="text-xs text-muted">{MODES.find((m) => m.value === mode)?.hint.replace("{noun}", SCOPES.find((x) => x.value === scope)!.noun)} Requests are spaced out per site; a full run can take a while, and you can leave this page.</p>
      {go.error && <p className="text-sm text-danger">{fetchErrorText(go.error)}</p>}
      <FetchProgress job={show} live={!!running} />
    </div>
  );
}
