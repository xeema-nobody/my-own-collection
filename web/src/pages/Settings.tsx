import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

export default function Settings() {
  const [set, setSet] = useState("");
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const sets = useQuery({ queryKey: ["sets"], queryFn: api.sets });
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.jobs, refetchInterval: 3000 });
  const imp = useMutation({ mutationFn: () => api.importCatalog(set || undefined) });
  const ref = useMutation({ mutationFn: (scope: string) => api.refreshPrices(scope) });
  const s = status.data;
  return (
    <div className="space-y-4">
      <section className="card"><h2 className="mb-2 font-semibold">Catalog</h2>
        <div className="flex flex-wrap items-center gap-2">
          <input className="input" list="setids" placeholder="set id (e.g. base1) — empty = full catalog" value={set} onChange={(e) => setSet(e.target.value)} />
          <datalist id="setids">{sets.data?.map((x: any) => <option key={x.id} value={x.external_id}>{x.name}</option>)}</datalist>
          <button className="btn" onClick={() => imp.mutate()}>Import</button>
          <button className="btn-ghost" onClick={() => ref.mutate("collection")}>Refresh collection prices</button>
          <button className="btn-ghost" onClick={() => ref.mutate("all")}>Refresh all prices</button>
        </div>
        <p className="mt-2 text-xs opacity-70">Imports run in the background; the first import also lists all sets. Progress below.</p></section>
      {s && <section className="card text-sm"><h2 className="mb-2 font-semibold">Config</h2>
        <p>Base currency: {s.base_currency} · Scheduler: {s.scheduler_enabled ? `on (${s.price_refresh_cron})` : "off (manual)"}</p>
        <p>Providers: {Object.entries(s.providers).map(([k, v]) => `${k}: ${v ? "enabled" : "disabled"}`).join(" · ")}</p></section>}
      <section className="card"><h2 className="mb-2 font-semibold">Jobs</h2>
        <table className="w-full text-sm"><tbody>{jobs.data?.map((j: any) => (
          <tr key={j.id} className="border-t dark:border-slate-700"><td>{j.type}</td><td>{j.status}</td><td>{j.started_at.slice(0, 19)}</td><td>{JSON.stringify(j.stats)}</td><td className="text-red-500">{j.error}</td></tr>))}</tbody></table></section>
    </div>
  );
}
