import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, FETCHER_START_CMD, SCRAPED_SOURCES } from "../lib/api";
import { errorText, QueryError } from "../components/QueryState";
import FetcherBadge from "../components/FetcherBadge";
import FetchProgress from "../components/FetchProgress";

export default function Settings() {
  const qc = useQueryClient();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [scope, setScope] = useState<"sets" | "owned">("sets");
  const [fSources, setFSources] = useState<string[]>([...SCRAPED_SOURCES]);
  const [force, setForce] = useState(false);
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const sets = useQuery({ queryKey: ["sets", "stats"], queryFn: () => api.sets(true) });
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.jobs, refetchInterval: 3000 });
  const done = () => { qc.invalidateQueries({ queryKey: ["jobs"] }); qc.invalidateQueries({ queryKey: ["sets"] }); };
  const imp = useMutation({ mutationFn: (ids?: string[]) => api.importCatalog(ids), onSettled: done });
  const retry = useMutation({ mutationFn: api.retryFailedImports, onSettled: done });
  const ref = useMutation({ mutationFn: (a: { scope: string; sets?: string[] }) => api.refreshPrices(a.scope, a.sets), onSettled: done });
  const fetchAll = useMutation({
    mutationFn: () => api.fetchPrices({ ...(scope === "owned" ? { owned: true } : { sets: [...picked] }), sources: fSources, force }),
    onSettled: done,
  });
  const running = (type: string) => jobs.data?.find((j: any) => j.type === type && j.status === "running");
  const importing = !!running("catalog_import"), refreshing = !!running("price_refresh");
  const lastFull = jobs.data?.find((j: any) => j.type === "catalog_import" && j.status !== "running" &&
    (["full", "retry"].includes(j.stats?.origin) || (!j.stats?.origin && !j.stats?.set)));
  const failed: string[] = lastFull?.stats?.failed_sets ?? [];
  const ids = [...picked];
  const shown = (sets.data ?? []).filter((x: any) =>
    `${x.name} ${x.external_id}`.toLowerCase().includes(filter.toLowerCase()));
  const toggle = (id: string) => setPicked((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const fetching = !!running("price_fetch");
  const lastFetch = jobs.data?.find((j: any) => j.type === "price_fetch");
  const fetchErr = fetchAll.error instanceof ApiError && fetchAll.error.status === 503
    ? `Fetcher not reachable. Start it on the host: ${FETCHER_START_CMD}`
    : fetchAll.error instanceof ApiError && fetchAll.error.status === 409 ? "A price fetch is already running."
    : fetchAll.error ? errorText(fetchAll.error) : null;
  const [file, setFile] = useState<File | null>(null);
  const [impMode, setImpMode] = useState<"set" | "add">("set");
  const xfer = useMutation({
    mutationFn: () => api.importCollection(file!, file!.name.toLowerCase().endsWith(".csv") ? "csv" : "json", impMode),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["collection"] }),
  });
  const err = imp.error || retry.error || ref.error;
  const s = status.data;
  return (
    <div className="space-y-4">
      <QueryError q={status} label="Status" /><QueryError q={sets} label="Sets" /><QueryError q={jobs} label="Jobs" />
      <section className="card"><h2 className="mb-2 font-semibold">Catalog &amp; prices</h2>
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn" disabled={importing || !ids.length} onClick={() => imp.mutate(ids)}>Import selected ({ids.length})</button>
          <button className="btn" disabled={refreshing || !ids.length} onClick={() => ref.mutate({ scope: "sets", sets: ids })}>Refresh prices for selected</button>
          <button className="btn-ghost" disabled={importing || !failed.length} onClick={() => retry.mutate()}>Retry failed imports ({failed.length})</button>
          <button className="btn-ghost" disabled={importing} onClick={() => imp.mutate(undefined)}>Import all</button>
          <button className="btn-ghost" disabled={refreshing} onClick={() => ref.mutate({ scope: "collection" })}>Refresh collection prices</button>
          <button className="btn-ghost" disabled={refreshing} onClick={() => ref.mutate({ scope: "all" })}>Refresh all prices</button>
        </div>
        {err && <p className="mt-2 text-sm text-red-500">{errorText(err)}</p>}
        {(importing || refreshing) && <p className="mt-2 text-sm text-amber-500">
          Running: {[running("catalog_import"), running("price_refresh")].filter(Boolean)
            .map((j: any) => `${j.type} ${JSON.stringify(j.stats)}`).join(" · ")}</p>}
        {failed.length > 0 && <p className="mt-2 text-xs opacity-70">Failed in last full import: {failed.join(", ")}</p>}
        <input className="input mt-3 w-full" placeholder="Filter sets by name or id…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <div className="mt-2 flex gap-2 text-xs">
          <button className="underline" onClick={() => setPicked(new Set(shown.map((x: any) => x.external_id)))}>select shown</button>
          <button className="underline" onClick={() => setPicked(new Set())}>clear</button>
          <button className="underline" onClick={() => setPicked(new Set(failed))}>select failed</button>
        </div>
        <ul className="mt-2 max-h-80 overflow-y-auto text-sm">
          {shown.map((x: any) => (
            <li key={x.external_id}><label className="flex cursor-pointer items-center gap-2 py-0.5">
              <input type="checkbox" checked={picked.has(x.external_id)} onChange={() => toggle(x.external_id)} />
              <span>{x.name}</span><span className="opacity-60">{x.external_id}</span>
              <span className="ml-auto tabular-nums">{x.cards_priced} / {x.cards_total} priced</span>
              {x.cards_total === 0 && <span className="text-amber-500">not imported</span>}
              {x.cards_total > 0 && x.cards_priced === 0 && <span className="text-slate-400" title="No price block in the source payload">no price source</span>}
            </label></li>))}
        </ul>
        <p className="mt-2 text-xs opacity-70">Imports run in the background; one job per type at a time. Progress below.</p></section>
      <section className="card text-sm"><h2 className="mb-2 font-semibold">Fetch scraped prices</h2>
        <p className="mb-2 opacity-70">Sold and graded prices from PriceCharting, Cardmarket and alt.xyz through the host fetcher (24 h cache). Runs on demand only.</p>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1"><input type="radio" checked={scope === "sets"} onChange={() => setScope("sets")} />Selected sets ({ids.length})</label>
          <label className="flex items-center gap-1"><input type="radio" checked={scope === "owned"} onChange={() => setScope("owned")} />Owned collection</label>
          {SCRAPED_SOURCES.map((x) => (
            <label key={x} className="flex items-center gap-1"><input type="checkbox" checked={fSources.includes(x)}
              onChange={() => setFSources((v) => v.includes(x) ? v.filter((y) => y !== x) : [...v, x])} />{x}</label>))}
          <label className="flex items-center gap-1" title="Ignore the 24 h cache"><input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />force</label>
          <button className="btn" disabled={fetching || fetchAll.isPending || !fSources.length || (scope === "sets" && !ids.length)} onClick={() => fetchAll.mutate()}>Fetch prices</button>
          <FetcherBadge />
        </div>
        {fetchErr && <p className="mt-2 text-red-500">{fetchErr}</p>}
        <FetchProgress job={lastFetch} live={fetching} />
      </section>
      {s && <section className="card text-sm"><h2 className="mb-2 font-semibold">Config</h2>
        <p>Base currency: {s.base_currency} · Scheduler: {s.scheduler_enabled ? "on" : "off (manual)"}</p>
        {s.scheduler_enabled && <ul className="text-xs opacity-80">{s.scheduler.jobs.map((j: any) => <li key={j.id}>{j.id}: next {j.next_run?.slice(0, 16).replace("T", " ")}</li>)}</ul>}
        <table className="mt-2 w-full"><thead><tr className="text-left opacity-70"><th>Price source</th><th>Kinds</th><th>Grades</th><th>Status</th></tr></thead><tbody>
          {s.price_sources.map((p: any) => <tr key={p.id} className="border-t dark:border-slate-700" title={p.note}><td>{p.label}</td><td>{p.kinds.join(", ")}</td><td>{p.grades}</td>
            <td className={p.enabled ? "text-emerald-600" : "opacity-60"}>{p.enabled ? "enabled" : "not available yet"}</td></tr>)}</tbody></table></section>}
      <section className="card text-sm"><h2 className="mb-2 font-semibold">Export / import collection</h2>
        <div className="flex flex-wrap items-center gap-2">
          <a className="btn" href={api.exportCollectionUrl("json")}>Export JSON</a>
          <a className="btn" href={api.exportCollectionUrl("csv")}>Export CSV</a>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input type="file" accept=".json,.csv" onChange={(e) => { setFile(e.target.files?.[0] ?? null); xfer.reset(); }} />
          <select className="input" value={impMode} onChange={(e) => setImpMode(e.target.value as "set" | "add")}>
            <option value="set">set quantities (re-import is a no-op)</option>
            <option value="add">add to quantities</option>
          </select>
          <button className="btn" disabled={!file || xfer.isPending} onClick={() => xfer.mutate()}>Import</button>
        </div>
        {xfer.data && <div className="mt-2">Created {xfer.data.created}, updated {xfer.data.updated}, {xfer.data.errors.length} rejected.
          <ul className="text-xs text-red-500">{xfer.data.errors.slice(0, 10).map((e) => <li key={e.row}>row {e.row}: {e.error}</li>)}</ul></div>}
        {xfer.error && <p className="mt-2 text-red-500">{errorText(xfer.error)}</p>}
      </section>
      <section className="card"><h2 className="mb-2 font-semibold">Jobs</h2>
        <table className="w-full text-sm"><tbody>{jobs.data?.map((j: any) => (
          <tr key={j.id} className="border-t dark:border-slate-700"><td>{j.type}</td><td>{j.status}</td><td className="opacity-70" title={j.error ?? ""}>{j.trigger ?? "manual"}</td><td>{j.started_at.slice(0, 19)}</td><td>{JSON.stringify(j.stats)}</td><td className="text-red-500">{j.error}</td></tr>))}</tbody></table></section>
    </div>
  );
}
