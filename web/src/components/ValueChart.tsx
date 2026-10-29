import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../lib/api";
import { Section, SegmentedControl, EmptyState, Skeleton } from "./ui";
import { QueryError } from "./QueryState";

const RANGES = { "30d": 30, "90d": 90, "1y": 365, all: 3650 } as const;
type Range = keyof typeof RANGES;
const eur = (v: unknown) => money(Math.round(Number(v) * 100));

/** Collection value and cost over time from the daily snapshots (valuation-version-2 snapshots only). */
export default function ValueChart() {
  const [range, setRange] = useState<Range>("90d");
  const q = useQuery({ queryKey: ["history", range], queryFn: () => api.history(RANGES[range]) });
  const rows = (q.data ?? []).filter((s: any) => s.total_value != null)
    .map((s: any) => ({ date: s.date, value: s.total_value / 100, cost: s.total_cost != null ? s.total_cost / 100 : undefined }));
  const hasCost = rows.some((r: any) => r.cost != null);
  return (
    <Section title="Value over time" actions={
      <SegmentedControl label="Range" value={range} onChange={setRange} options={(Object.keys(RANGES) as Range[]).map((r) => ({ value: r, label: r }))} />}>
      <QueryError q={q} label="History" />
      {q.isLoading && <Skeleton className="h-48 w-full" />}
      {q.data && rows.length === 0 && <EmptyState title="No history yet">Snapshots are taken daily; run "Snapshot now" on the Dashboard to add one.</EmptyState>}
      {rows.length === 1 && <p className="num text-sm">{rows[0].date}: <span className="font-semibold">{eur(rows[0].value)}</span> <span className="text-muted">(one snapshot so far)</span></p>}
      {rows.length > 1 && (
        <div className="h-48 text-muted" role="img" aria-label="Collection value over time">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.2} />
              <XAxis dataKey="date" tick={{ fill: "currentColor", fontSize: 11 }} stroke="currentColor" strokeOpacity={0.3} minTickGap={32} />
              <YAxis tick={{ fill: "currentColor", fontSize: 11 }} stroke="currentColor" strokeOpacity={0.3} width={56} tickFormatter={(v) => String(Math.round(v))} />
              <Tooltip formatter={(v: any, n: any) => [eur(v), n]} contentStyle={{ background: "rgb(var(--surface))", border: "1px solid rgb(var(--line))", borderRadius: 8, color: "rgb(var(--fg))" }} />
              <Line type="monotone" dataKey="value" name="Value" dot={rows.length < 15} strokeWidth={2} className="text-accent" stroke="currentColor" />
              {hasCost && <Line type="stepAfter" dataKey="cost" name="Cost" dot={false} strokeWidth={1.5} strokeDasharray="4 3" stroke="currentColor" />}
            </LineChart>
          </ResponsiveContainer>
        </div>)}
    </Section>);
}
