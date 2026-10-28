import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

/** Running `price_fetch` job (shares the ["jobs"] query with Settings). `onFinish` fires once when it ends. */
export function usePriceFetchJob(onFinish?: (job: any) => void) {
  const jobs = useQuery({
    queryKey: ["jobs"], queryFn: api.jobs,
    refetchInterval: (q) => (q.state.data?.some((j: any) => j.type === "price_fetch" && j.status === "running") ? 2000 : 5000),
  });
  const latest = jobs.data?.find((j: any) => j.type === "price_fetch");
  const running = latest?.status === "running" ? latest : undefined;
  const prev = useRef<string | undefined>(undefined);
  useEffect(() => {
    // Only react to a job we saw running (not to old finished ones on first load).
    if (running) prev.current = latest.id;
    else if (prev.current && latest?.id === prev.current) { prev.current = undefined; onFinish?.(latest); }
  }, [running, latest?.id, latest?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  return { running, latest };
}
