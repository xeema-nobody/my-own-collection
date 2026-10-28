import { Link } from "react-router-dom";

const Item = ({ x }: { x: any }) => (
  <li><Link className="underline" to={`/cards/${encodeURIComponent(x.card_id)}`}>{x.card_id}</Link> · {x.source}
    {x.status && <span className="opacity-70"> · {x.status}{x.detail ? `: ${x.detail}` : ""}</span>}</li>);

/** Progress / result of a `price_fetch` job (`job.stats`). */
export default function FetchProgress({ job, live }: { job: any; live: boolean }) {
  const s = job?.stats;
  if (!s) return null;
  return (
    <div className="mt-2 space-y-1 text-sm">
      {live && s.waiting_login?.length > 0 && (
        <p className="rounded bg-amber-100 p-2 text-amber-900 dark:bg-amber-900 dark:text-amber-100">
          Waiting for login ({s.waiting_login.join(", ")}) – look at the Chrome window.</p>)}
      <p className={live ? "text-amber-500" : "opacity-80"}>
        {live ? "Fetching" : `Last fetch (${job.status})`} {s.done}/{s.total}
        {live && s.current && <> · now {s.current.card_id} · {s.current.source}</>}
        {" "}· ok {s.ok} · failed {s.failed} · needs match {s.needs_match} · not found {s.not_found} · cached {s.skipped_cached}
        {s.skipped_site > 0 && <> · skipped (site) {s.skipped_site}</>} · new sales {s.sales_new} · seeded {s.seeded}
        {job.error && <span className="text-red-500"> · {job.error}</span>}</p>
      {s.failures?.length > 0 && <details><summary className="cursor-pointer">Failures ({s.failures.length})</summary>
        <ul className="ml-4 list-disc">{s.failures.map((x: any, i: number) => <Item key={i} x={x} />)}</ul></details>}
      {s.needs_match_list?.length > 0 && <details><summary className="cursor-pointer">Needs match ({s.needs_match_list.length})</summary>
        <ul className="ml-4 list-disc">{s.needs_match_list.map((x: any, i: number) => <Item key={i} x={x} />)}</ul></details>}
    </div>
  );
}
