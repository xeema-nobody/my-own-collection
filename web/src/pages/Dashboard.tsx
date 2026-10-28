import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../lib/api";
import { SOURCE_COLOR } from "../lib/colors";

const RANGES: Record<string, number> = { "7d": 7, "30d": 30, "90d": 90, "1y": 365, all: 3650 };

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

  const rows = (hist.data ?? []).map((s: any) => ({ date: s.date, ...(s.total_value != null && { total: s.total_value / 100 }), ...Object.fromEntries(Object.entries(s.totals_by_source).map(([k, v]: any) => [k, v / 100])) }));
  // Snapshots before Phase 4 valued slabs at raw price and lack total_value: not comparable, so the
  // change % only spans snapshots that have it.
  const cmp = (hist.data ?? []).filter((s: any) => s.total_value != null);
  const cur = cmp.length > 1 ? cmp.at(-1).total_value : null;
  const old = cmp.length > 1 ? cmp[0].total_value : null;
  const delta = cur != null && old ? ((cur - old) / old) * 100 : null;
  const lastRun = jobs.data?.find((j: any) => j.type === "price_refresh");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn" disabled={refresh.isPending} onClick={() => refresh.mutate()}>Refresh prices</button>
        <button className="btn-ghost" onClick={() => snap.mutate()}>Snapshot now</button>
        <span className="text-sm opacity-70">Last refresh: {lastRun ? `${lastRun.finished_at?.slice(0, 16) ?? "running"} (${lastRun.status})` : "never"}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="card"><div className="text-xs opacity-70">Value</div><div className="text-xl font-semibold">{money(sum.data?.value)}</div>
          {sum.data?.estimated > 0 && <div className="text-xs opacity-70">{sum.data.estimated} estimated (≈ in Collection)</div>}</div>
        <div className="card"><div className="text-xs opacity-70">Cost</div><div className="text-xl font-semibold">{money(sum.data?.cost)}</div></div>
        <div className="card"><div className="text-xs opacity-70">P/L</div><div className="text-xl font-semibold">{sum.data?.pl == null ? "—" : money(sum.data.pl)}</div></div>
        <div className="card"><div className="text-xs opacity-70">Change ({range})</div>
          <div className={`text-xl font-semibold ${delta == null ? "" : delta >= 0 ? "text-emerald-600" : "text-red-500"}`}>{delta == null ? "—" : `${delta >= 0 ? "▲" : "▼"} ${delta.toFixed(1)}%`}</div></div>
      </div>
      <section className="card">
        <div className="mb-2 flex gap-1">{Object.keys(RANGES).map((r) => <button key={r} className={r === range ? "btn" : "btn-ghost"} onClick={() => setRange(r)}>{r}</button>)}</div>
        {rows.length < 2 ? <p className="py-10 text-center text-sm opacity-70">History starts at the first snapshot ({rows.length} so far). No past prices can be backfilled; snapshots are taken after each price refresh.</p> :
          <div className="h-72"><ResponsiveContainer><LineChart data={rows}><CartesianGrid strokeDasharray="3 3" opacity={0.3} /><XAxis dataKey="date" /><YAxis /><Tooltip /><Legend />
            {rows.some((r: any) => "total" in r) && <Line dataKey="total" name="value (best)" stroke="#6366f1" strokeWidth={3} dot={false} />}
            {Object.keys(SOURCE_COLOR).filter((k) => rows.some((r: any) => k in r)).map((k) => <Line key={k} dataKey={k} stroke={SOURCE_COLOR[k]} dot={false} />)}</LineChart></ResponsiveContainer></div>}
      </section>
      <div className="grid gap-4 md:grid-cols-2">
        <section className="card"><div className="mb-2 flex gap-1">{["set", "rarity", "condition", "language", "tcg"].map((b) => <button key={b} className={b === by ? "btn" : "btn-ghost"} onClick={() => setBy(b)}>{b}</button>)}</div>
          <div className="h-64"><ResponsiveContainer><BarChart data={(brk.data ?? []).map((r: any) => ({ ...r, value: r.value / 100 }))} layout="vertical"><CartesianGrid opacity={0.3} /><XAxis type="number" /><YAxis type="category" dataKey="name" width={110} /><Tooltip /><Bar dataKey="value" fill="#6366f1" /></BarChart></ResponsiveContainer></div></section>
        <section className="card"><h2 className="mb-2 font-semibold">Top movers (7d)</h2>
          {!mov.data?.up.length && !mov.data?.down.length && <p className="text-sm opacity-70">Needs ≥2 price points in the window.</p>}
          {[...(mov.data?.up ?? []), ...(mov.data?.down ?? [])].map((m: any) => <div key={m.card_id} className="flex justify-between text-sm"><span>{m.name}</span><span className={m.pct >= 0 ? "text-emerald-600" : "text-red-500"}>{m.pct >= 0 ? "▲" : "▼"} {m.pct}%</span></div>)}</section>
      </div>
    </div>
  );
}
