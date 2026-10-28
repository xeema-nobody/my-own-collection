import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../lib/api";
import { QueryError } from "../components/QueryState";
import { KIND_CLASS, SOURCE_COLOR } from "../lib/colors";

const RANGES: Record<string, number> = { "7d": 7, "30d": 30, "90d": 90, "1y": 365, all: 3650 };
/** Chart values are euros (cents / 100); format them like the rest of the app. */
const eur = (v: any) => money(Math.round(Number(v) * 100));
/** Hollow dot = that source valued something thin or not exact (bucket / lower / raw fallback) that day. */
const dotFor = (color: string, weakKey: string) => (p: any) =>
  <circle key={`${weakKey}-${p.index}`} cx={p.cx} cy={p.cy} r={3} stroke={color} strokeWidth={2} fill={p.payload[weakKey] ? "none" : color} />;

export default function Dashboard() {
  const [range, setRange] = useState("90d");
  const [by, setBy] = useState("set");
  const qc = useQueryClient();
  const hist = useQuery({ queryKey: ["history", range], queryFn: () => api.history(RANGES[range]) });
  const brk = useQuery({ queryKey: ["breakdown", by], queryFn: () => api.breakdown(by) });
  const mov = useQuery({ queryKey: ["movers"], queryFn: () => api.movers(7) });
  const sum = useQuery({ queryKey: ["collection", "summary"], queryFn: api.collectionSummary });
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.jobs, refetchInterval: 5000 });
  const refresh = useMutation({ mutationFn: () => api.refreshPrices("collection"), onSuccess: () => qc.invalidateQueries() });
  const snap = useMutation({ mutationFn: api.snapshot, onSuccess: () => qc.invalidateQueries({ queryKey: ["history"] }) });

  // Per-source totals of snapshots before Phase 4 valued slabs at raw price (no total_value): not plotted.
  const rows = (hist.data ?? []).filter((s: any) => s.total_value != null).map((s: any) => ({
    date: s.date,
    total: s.total_value / 100,
    ...Object.fromEntries(Object.entries(s.totals_by_source).flatMap(([k, v]: any) => [[k, v / 100], [`weak_${k}`, !!s.weak_by_source?.[k]]])),
  }));
  const legacy = (hist.data ?? []).filter((s: any) => s.total_value == null).length;
  // Snapshots before Phase 4 valued slabs at raw price and lack total_value: not comparable, so the
  // change % only spans snapshots that have it.
  const cmp = (hist.data ?? []).filter((s: any) => s.total_value != null);
  const cur = cmp.length > 1 ? cmp.at(-1).total_value : null;
  const old = cmp.length > 1 ? cmp[0].total_value : null;
  const delta = cur != null && old ? ((cur - old) / old) * 100 : null;
  const soldPct = sum.data?.value ? Math.round(((sum.data.value_by_kind?.sold ?? 0) / sum.data.value) * 100) : null;
  const lastRun = jobs.data?.find((j: any) => j.type === "price_refresh");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn" disabled={refresh.isPending} onClick={() => refresh.mutate()}>Refresh prices</button>
        <button className="btn-ghost" onClick={() => snap.mutate()}>Snapshot now</button>
        <span className="text-sm opacity-70">Last refresh: {lastRun ? `${lastRun.finished_at?.slice(0, 16) ?? "running"} (${lastRun.status})` : "never"}</span>
      </div>
      <QueryError q={sum} label="Summary" /><QueryError q={hist} label="History" /><QueryError q={brk} label="Breakdown" /><QueryError q={mov} label="Movers" /><QueryError q={jobs} label="Jobs" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <div className="card"><div className="text-xs opacity-70">Value</div><div className="text-xl font-semibold">{money(sum.data?.value)}</div>
          {sum.data?.estimated > 0 && <div className="text-xs opacity-70">{sum.data.estimated} estimated (≈ in Collection)</div>}</div>
        <div className="card"><div className="text-xs opacity-70">Reliability</div><div className="text-xl font-semibold">{soldPct == null ? "—" : `${soldPct}% sold-based`}</div>
          <div className="text-xs opacity-70">{sum.data?.unpriced ? `${sum.data.unpriced} unpriced · ` : ""}{sum.data?.estimated ?? 0} estimated</div></div>
        <div className="card"><div className="text-xs opacity-70">Cost</div><div className="text-xl font-semibold">{money(sum.data?.cost)}</div></div>
        <div className="card"><div className="text-xs opacity-70">P/L</div><div className="text-xl font-semibold">{sum.data?.pl == null ? "—" : money(sum.data.pl)}</div></div>
        <div className="card"><div className="text-xs opacity-70">Change ({range})</div>
          <div className={`text-xl font-semibold ${delta == null ? "" : delta >= 0 ? "text-emerald-600" : "text-red-500"}`}>{delta == null ? "—" : `${delta >= 0 ? "▲" : "▼"} ${delta.toFixed(1)}%`}</div></div>
      </div>
      <section className="card"><h2 className="mb-2 font-semibold">Source comparison</h2>
        <table className="w-full text-sm"><thead><tr className="text-left text-xs opacity-60"><th>Source</th><th>Total</th><th>Items priced</th><th>vs headline (same items)</th></tr></thead><tbody>
          {Object.entries(sum.data?.by_source ?? {}).map(([k, v]: any) => (
            <tr key={k} className="border-t dark:border-slate-700"><td style={{ color: SOURCE_COLOR[k] }}>{k}</td><td>{money(v.value)}</td>
              <td>{v.items}/{sum.data.distinct}</td>
              <td>{v.vs_headline_pct == null ? "—" : <span className={v.far ? "rounded bg-amber-100 px-1 text-amber-800 dark:bg-amber-900 dark:text-amber-200" : "opacity-70"} title={v.far ? "Far from the headline valuation" : ""}>{v.vs_headline_pct > 0 ? "+" : ""}{v.vs_headline_pct}%{v.far ? " ⚠" : ""}</span>}</td></tr>))}
        </tbody></table>
        <p className="mt-1 text-xs opacity-60">Headline = best price per item (sold first, then preferred source). Totals per source use only that source and may cover fewer items.</p>
      </section>
      <section className="card">
        <div className="mb-2 flex gap-1">{Object.keys(RANGES).map((r) => <button key={r} className={r === range ? "btn" : "btn-ghost"} onClick={() => setRange(r)}>{r}</button>)}</div>
        {rows.length < 2 ? <p className="py-10 text-center text-sm opacity-70">History starts at the first snapshot ({rows.length} so far). No past prices can be backfilled; snapshots are taken after each price refresh.{legacy > 0 && ` ${legacy} older snapshot(s) predate graded valuation and are not plotted.`}</p> :
          <div className="h-72"><ResponsiveContainer><LineChart data={rows}><CartesianGrid strokeDasharray="3 3" opacity={0.3} /><XAxis dataKey="date" /><YAxis tickFormatter={eur} width={80} /><Tooltip formatter={eur} /><Legend />
            {rows.some((r: any) => "total" in r) && <Line dataKey="total" name="value (best)" stroke="#6366f1" strokeWidth={3} dot={{ r: 3 }} connectNulls />}
            {Object.keys(SOURCE_COLOR).filter((k) => rows.some((r: any) => k in r)).map((k) => <Line key={k} dataKey={k} stroke={SOURCE_COLOR[k]} dot={dotFor(SOURCE_COLOR[k], `weak_${k}`)} connectNulls />)}</LineChart></ResponsiveContainer></div>}
      </section>
      <div className="grid gap-4 md:grid-cols-2">
        <section className="card"><div className="mb-2 flex gap-1">{["set", "rarity", "condition", "language", "tcg"].map((b) => <button key={b} className={b === by ? "btn" : "btn-ghost"} onClick={() => setBy(b)}>{b}</button>)}</div>
          <div className="h-64"><ResponsiveContainer><BarChart data={(brk.data ?? []).map((r: any) => ({ ...r, value: r.value / 100 }))} layout="vertical"><CartesianGrid opacity={0.3} /><XAxis type="number" tickFormatter={eur} /><YAxis type="category" dataKey="name" width={110} /><Tooltip formatter={eur} /><Bar dataKey="value" fill="#6366f1" /></BarChart></ResponsiveContainer></div></section>
        <section className="card"><h2 className="mb-2 font-semibold">Top movers (7d)</h2>
          {!mov.data?.up.length && !mov.data?.down.length && <p className="text-sm opacity-70">{sum.data?.distinct === 0 ? "No cards owned yet: add some from Search." : "No moves yet. An item needs the same kind of price (sold / market, same grade match) today and 7 days ago."}</p>}
          {[...(mov.data?.up ?? []), ...(mov.data?.down ?? [])].map((m: any) => (
            <div key={`${m.card_id}-${m.grade_key}`} className="flex items-center justify-between gap-2 text-sm" title={`via ${m.source}${m.match === "exact" ? "" : ` (${m.match})`}`}>
              <span>{m.name} <span className="opacity-60">{m.grade_key === "raw" ? "raw" : m.grade_key}</span> <span className={`rounded px-1 text-xs ${KIND_CLASS[m.kind] ?? ""}`}>{m.kind}</span></span>
              <span className="whitespace-nowrap"><span className="opacity-60">{money(m.from)} → {money(m.to)}</span> <span className={m.pct >= 0 ? "text-emerald-600" : "text-red-500"}>{m.pct >= 0 ? "▲" : "▼"} {m.pct}%</span></span>
            </div>))}</section>
      </div>
    </div>
  );
}
