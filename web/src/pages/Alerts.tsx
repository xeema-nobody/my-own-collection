import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ago, api, money, type AlertEvent, type AlertIn, type AlertRule } from "../lib/api";
import { QueryError } from "../components/QueryState";
import { KIND_CLASS } from "../lib/colors";

const OPS = { above: "goes above", below: "drops below", up_pct: "rises by", down_pct: "falls by" } as const;
const isPct = (op: string) => op.endsWith("_pct");

function Inbox() {
  const qc = useQueryClient();
  const ev = useQuery({ queryKey: ["alerts", "events"], queryFn: () => api.alertEvents() });
  const read = useMutation({
    mutationFn: (ids?: string[]) => api.markAlertsRead(ids),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const unread = (ev.data ?? []).filter((e) => !e.read);
  const line = (e: AlertEvent) => e.type === "system"
    ? <span>⚠ {e.rule}</span>
    : <span><b>{e.name}</b>: {e.rule} — now {money(e.value)}
      {e.prev != null && <span className="opacity-70"> (was {money(e.prev)}, {e.pct! > 0 ? "+" : ""}{e.pct}%)</span>}
      {e.price_kind && <span className={`ml-1 rounded px-1 text-xs ${KIND_CLASS[e.price_kind] ?? ""}`}>{e.price_kind}</span>}
      {e.thin && <span className="ml-1 text-xs text-amber-600 dark:text-amber-400">thin data</span>}
      {e.estimated && <span className="ml-1 text-xs text-amber-600 dark:text-amber-400">estimated</span>}</span>;
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-3"><h2 className="text-lg font-semibold">Inbox</h2>
        <button className="btn-ghost" disabled={!unread.length} onClick={() => read.mutate(undefined)}>Mark all read</button></div>
      <QueryError q={ev} label="Inbox" />
      {ev.isLoading && <p className="opacity-70">Loading…</p>}
      {ev.data?.length === 0 && <p className="opacity-70">No alerts yet. Rules are checked after every price fetch, refresh and snapshot.</p>}
      <ul className="space-y-1">
        {ev.data?.map((e) => (
          <li key={e.id} className={`card flex items-center justify-between gap-3 text-sm ${e.read ? "opacity-60" : ""}`}>
            <div>{line(e)} <span className="ml-2 text-xs opacity-70">{ago(e.fired_at)}</span>
              {e.card_id && <Link className="ml-2 text-xs underline" to={`/cards/${encodeURIComponent(e.card_id)}`}>card</Link>}</div>
            {!e.read && <button className="btn-ghost text-xs" onClick={() => read.mutate([e.id])}>Mark read</button>}
          </li>))}
      </ul>
    </section>
  );
}

function RuleForm() {
  const qc = useQueryClient();
  const items = useQuery({ queryKey: ["collection", "alert-targets"], queryFn: () => api.collection({ page_size: 200 }) });
  const [f, setF] = useState({ scope: "stack", target: "", op: "above", amount: "", days: "7", kind: "any", est: false });
  const [err, setErr] = useState("");
  const rows: any[] = items.data?.items ?? [];
  const create = useMutation({
    mutationFn: (b: AlertIn) => api.createAlert(b),
    onSuccess: () => { setErr(""); setF({ ...f, amount: "" }); qc.invalidateQueries({ queryKey: ["alerts"] }); },
    onError: (e: Error) => setErr(e.message),
  });
  const cardOptions = [...new Map(rows.map((i) => [i.card_id, i.card?.name ?? i.card_id])).entries()];
  const submit = () => {
    const amount = parseFloat(f.amount);
    if (!(amount > 0)) return setErr("Enter an amount above 0");
    if (f.scope !== "total" && !f.target) return setErr("Pick a target");
    const b: AlertIn = { scope: f.scope, op: f.op, kind: f.kind, include_estimated: f.est,
      threshold: isPct(f.op) ? amount : Math.round(amount * 100) };
    if (f.scope === "stack") b.item_id = f.target;
    if (f.scope === "card") b.card_id = f.target;
    if (isPct(f.op)) b.days = parseInt(f.days, 10);
    create.mutate(b);
  };
  return (
    <section className="card space-y-2">
      <h2 className="text-lg font-semibold">New rule</h2>
      <div className="flex flex-wrap items-center gap-2">
        <select className="input" aria-label="Scope" value={f.scope} onChange={(e) => setF({ ...f, scope: e.target.value, target: "" })}>
          <option value="stack">Stack</option><option value="card">Card (all stacks)</option><option value="total">Collection total</option></select>
        {f.scope === "stack" && <select className="input" aria-label="Stack" value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })}>
          <option value="">Pick a stack…</option>
          {rows.map((i) => <option key={i.id} value={i.id}>{i.card?.name} #{i.card?.number} · {i.grading ? `${i.grading.company} ${i.grading.grade}` : i.condition} × {i.quantity}</option>)}</select>}
        {f.scope === "card" && <select className="input" aria-label="Card" value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })}>
          <option value="">Pick a card…</option>{cardOptions.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select>}
        <select className="input" aria-label="Condition" value={f.op} onChange={(e) => setF({ ...f, op: e.target.value })}>
          {Object.entries(OPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <input className="input w-28" aria-label="Amount" inputMode="decimal" placeholder={isPct(f.op) ? "10 (%)" : "100.00 (EUR)"} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} />
        {isPct(f.op) && <label className="text-sm">over <input className="input w-16" aria-label="Days" inputMode="numeric" value={f.days} onChange={(e) => setF({ ...f, days: e.target.value })} /> days</label>}
        <select className="input" aria-label="Price kind" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
          <option value="any">any price</option><option value="sold">sold only</option><option value="market">market only</option></select>
        <label className="text-sm"><input type="checkbox" checked={f.est} onChange={(e) => setF({ ...f, est: e.target.checked })} /> include estimated</label>
        <button className="btn" disabled={create.isPending} onClick={submit}>Add rule</button>
      </div>
      <QueryError q={items} label="Stacks" />
      {err && <p role="alert" className="text-sm text-red-500">{err}</p>}
      <p className="text-xs opacity-70">Fires once when the condition becomes true and re-arms when it clears. A rule that is already true fires on the next check. Amounts are in EUR.</p>
    </section>
  );
}

function Rules() {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["alerts", "rules"], queryFn: api.alerts });
  const inval = () => qc.invalidateQueries({ queryKey: ["alerts"] });
  const toggle = useMutation({ mutationFn: (r: AlertRule) => api.patchAlert(r.id, { enabled: !r.enabled }), onSuccess: inval });
  const del = useMutation({ mutationFn: (id: string) => api.deleteAlert(id), onSuccess: inval });
  const check = useMutation({ mutationFn: api.evaluateAlerts, onSuccess: inval });
  // same query as the nav badge: Mark read in the Inbox refetches it, which clears the label
  const unread = useQuery({ queryKey: ["alerts", "unread"], queryFn: api.alertUnread });
  const fresh = Math.min(check.data?.fired ?? 0, unread.data?.count ?? 0);
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-3"><h2 className="text-lg font-semibold">Rules</h2>
        <button className="btn-ghost" disabled={check.isPending} onClick={() => check.mutate()}>Check now</button>
        {fresh > 0 && <span className="text-sm opacity-70">{fresh} new</span>}</div>
      <QueryError q={rules} label="Rules" />
      {rules.isLoading && <p className="opacity-70">Loading…</p>}
      {rules.data?.length === 0 && <p className="opacity-70">No rules yet.</p>}
      <table className="w-full text-sm"><tbody>
        {rules.data?.map((r) => (
          <tr key={r.id} className="border-t dark:border-slate-700">
            <td className="py-1.5">{r.description}{r.include_estimated && <span className="ml-1 text-xs opacity-70">(incl. estimated)</span>}</td>
            <td>{r.triggered ? <span className="text-amber-600 dark:text-amber-400">triggered</span> : <span className="opacity-70">armed</span>}</td>
            <td className="opacity-70">{r.last_value != null ? `last ${money(r.last_value)}` : "not priced yet"}{r.last_pct != null ? ` (${r.last_pct}%)` : ""}</td>
            <td className="text-right"><button className="btn-ghost mr-2 text-xs" onClick={() => toggle.mutate(r)}>{r.enabled ? "Disable" : "Enable"}</button>
              <button className="btn-ghost text-xs" onClick={() => del.mutate(r.id)}>Delete</button></td>
          </tr>))}
      </tbody></table>
    </section>
  );
}

export default function Alerts() {
  return <div className="space-y-6"><Inbox /><Rules /><RuleForm /></div>;
}
