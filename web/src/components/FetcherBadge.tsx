import { useQuery } from "@tanstack/react-query";
import { api, FETCHER_START_CMD } from "../lib/api";

export default function FetcherBadge() {
  const st = useQuery({ queryKey: ["fetcher-status"], queryFn: api.fetcherStatus, refetchInterval: 5000 });
  if (!st.data) return null;
  return st.data.up
    ? <span className="text-xs text-emerald-600" title={JSON.stringify(st.data.sites)}>● fetcher up (browser {st.data.browser})</span>
    : <span className="text-xs text-red-500">● fetcher not running – start it on the host: <code>{FETCHER_START_CMD}</code></span>;
}
