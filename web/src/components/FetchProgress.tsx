import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { etaText } from "../lib/fetchJob";
import { Badge, Button, Table, THead, Td, Th, Tr } from "./ui";

type Row = { card_id: string; name?: string | null; source: string; reason?: string; status?: string; detail?: string | null };
const reasonOf = (x: Row) => x.reason ?? x.status ?? "failed";

function AttentionTable({ rows }: { rows: Row[] }) {
  return (
    <Table><THead><Th>Card</Th><Th>Source</Th><Th>Reason</Th><Th>Detail</Th><Th><span className="sr-only">Action</span></Th></THead><tbody>
      {rows.map((x, i) => (
        <Tr key={i}>
          <Td><Link className="underline" to={`/cards/${encodeURIComponent(x.card_id)}`}>{x.name ?? x.card_id}</Link></Td>
          <Td className="text-muted">{x.source}</Td>
          <Td><Badge tone={reasonOf(x) === "no match" ? "warn" : "danger"}>{reasonOf(x)}</Badge></Td>
          <Td className="text-muted">{x.detail ?? ""}</Td>
          <Td>{reasonOf(x) === "no match" &&
            <Link className="text-accent underline" to={`/cards/${encodeURIComponent(x.card_id)}#card-sources`}>Choose match</Link>}</Td>
        </Tr>))}
    </tbody></Table>);
}

/** Progress / result of a `price_fetch` job (`job.stats`): pace, pause / cancel, failures, retry. */
export default function FetchProgress({ job, live }: { job: any; live: boolean }) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["jobs"] });
  const control = useMutation({ mutationFn: (a: "pause" | "resume" | "cancel") => api.fetchControl(a), onSettled: refresh });
  const retry = useMutation({ mutationFn: api.fetchRetry, onSettled: refresh });
  const s = job?.stats;
  if (!s) return null;
  const attention: Row[] = [...(s.failures ?? []), ...(s.needs_match_list ?? [])];
  const retryable = (s.failures ?? []).length > 0;
  const eta = live && !s.paused ? etaText(s.eta_s) : null;
  const err = control.error ?? retry.error;
  return (
    <div className="mt-2 space-y-2 text-sm">
      {live && s.waiting_login?.length > 0 && (
        <p className="rounded border-l-2 border-warn bg-surface-2 p-2">
          Waiting for login ({s.waiting_login.join(", ")}) – look at the Chrome window.</p>)}
      <p className={live ? "text-warn" : "text-muted"}>
        {live ? (s.paused ? "Paused" : "Fetching") : `Last fetch (${job.status})`}
        {s.scope && s.scope !== "collection" ? ` · ${s.scope}` : ""}{" "}
        <span className="num">{s.done} / {s.total} done, {s.failed} failed{eta ? `, ${eta}` : ""}</span>
        {live && s.current && !s.paused && <> · now {s.current.card_id} · {s.current.source}</>}
        <span className="text-muted"> · needs match {s.needs_match} · not found {s.not_found} · cached {s.skipped_cached}
          {s.skipped_site > 0 && <> · skipped (site) {s.skipped_site}</>} · new sales {s.sales_new} · seeded {s.seeded}</span>
        {job.error && <span className="text-danger"> · {job.error}</span>}</p>
      {live && (
        <div className="flex gap-2">
          {s.paused
            ? <Button size="sm" disabled={control.isPending} onClick={() => control.mutate("resume")}>Resume</Button>
            : <Button size="sm" variant="secondary" disabled={control.isPending} onClick={() => control.mutate("pause")}>Pause</Button>}
          <Button size="sm" variant="ghost" disabled={control.isPending} onClick={() => control.mutate("cancel")}>Cancel</Button>
        </div>)}
      {!live && job.status !== "running" && s.mode && (
        <p className="font-medium" role="status">
          {s.ok_cards ?? 0} cards updated{attention.length > 0 ? `, ${attention.length} need attention` : ""}
          {s.alerts_fired > 0 ? `, ${s.alerts_fired} alert${s.alerts_fired === 1 ? "" : "s"} fired` : ""}</p>)}
      {!live && attention.length > 0 && (
        <details open={attention.length <= 10}><summary className="cursor-pointer">Needs attention ({attention.length})</summary>
          <div className="mt-2 space-y-2">
            <AttentionTable rows={attention} />
            {retryable && <Button size="sm" disabled={retry.isPending} onClick={() => retry.mutate()}>Retry failed</Button>}
          </div></details>)}
      {live && attention.length > 0 && <p className="text-muted">{attention.length} need attention so far (listed when the run ends).</p>}
      {err && <p className="text-danger">{String((err as Error).message)}</p>}
    </div>
  );
}
