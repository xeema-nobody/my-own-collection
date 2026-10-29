import { useQuery } from "@tanstack/react-query";
import { api, FETCHER_START_CMD } from "../lib/api";

export default function FetcherBadge() {
  const st = useQuery({ queryKey: ["fetcher-status"], queryFn: api.fetcherStatus, refetchInterval: 5000 });
  if (!st.data) return null;
  return st.data.up
    ? <span className="flex items-center gap-1.5 text-xs text-muted" title={JSON.stringify(st.data.sites)}><span className="h-2 w-2 rounded-full bg-ok" />fetcher up</span>
    : <span className="flex items-center gap-1.5 text-xs text-danger" title={`Start it on the host: ${FETCHER_START_CMD}`}><span className="h-2 w-2 rounded-full bg-danger" />fetcher offline</span>;
}
