import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, FETCHER_START_CMD, SCRAPED_SOURCES } from "../lib/api";
import { usePriceFetchJob } from "../lib/fetchJob";
import { Button, Checkbox, Chip } from "./ui";
import FetcherBadge from "./FetcherBadge";
import FetchProgress from "./FetchProgress";

export const refreshCardPrices = (qc: ReturnType<typeof useQueryClient>, id: string) =>
  ["card", "matrix", "hist", "fetch-status", "match"].forEach((k) => qc.invalidateQueries({ queryKey: [k, id] }));

const errText = (e: unknown) => {
  if (e instanceof ApiError && e.status === 409) return "A price fetch is already running.";
  if (e instanceof ApiError && e.status === 503) return `Fetcher not reachable. Start it on the host: ${FETCHER_START_CMD}`;
  return String(e instanceof Error ? e.message : e);
};

export default function CardFetch({ cardId }: { cardId: string }) {
  const qc = useQueryClient();
  const [sources, setSources] = useState<string[]>([...SCRAPED_SOURCES]);
  const [force, setForce] = useState(false);
  const { running, latest } = usePriceFetchJob(() => refreshCardPrices(qc, cardId));
  const go = useMutation({
    mutationFn: () => api.fetchCardPrices(cardId, { sources, force }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
  const toggle = (s: string) => setSources((x) => (x.includes(s) ? x.filter((y) => y !== s) : [...x, s]));
  return (
    <div className="mb-3 border-b border-line pb-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <Button disabled={!!running || go.isPending || !sources.length} onClick={() => go.mutate()}>Fetch prices</Button>
        {SCRAPED_SOURCES.map((s) => <Chip key={s} active={sources.includes(s)} onClick={() => toggle(s)}>{s}</Chip>)}
        <Checkbox label="force" title="Ignore the 24 h cache" checked={force} onChange={(e) => setForce(e.target.checked)} />
        <FetcherBadge />
      </div>
      {go.error && <p className="mt-2 text-sm text-danger">{errText(go.error)}</p>}
      <FetchProgress job={running ?? (go.isSuccess ? latest : undefined)} live={!!running} />
    </div>
  );
}
