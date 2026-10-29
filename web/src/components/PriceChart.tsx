import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../lib/api";
import { SOURCE_COLOR, sourceLabel } from "../lib/colors";
import { gradeLabel } from "../lib/grades";
import type { PriceGrade } from "../lib/priceGrade";
import GradeSelector from "./GradeSelector";
import { Checkbox, Chip, SegmentedControl, SourceDot } from "./ui";

const DASH: Record<string, string | undefined> = { sold: undefined, market: "5 4", ask: "2 3" };
const RANGES = [["3m", 90], ["6m", 180], ["1y", 365], ["all", 0]] as const;
type Range = (typeof RANGES)[number][0];
const seriesName = (k: string) => { const [s, kind, v] = k.split(":"); return `${sourceLabel(s)} · ${kind}${v ? ` (${v})` : ""}`; };

export default function PriceChart({ cardId, pg }: { cardId: string; pg: PriceGrade }) {
  const [range, setRange] = useState<Range>("all");
  const [off, setOff] = useState<Set<string>>(new Set());
  const [ask, setAsk] = useState(false);
  const days = RANGES.find((r) => r[0] === range)![1] || undefined;
  const hist = useQuery({ queryKey: ["hist", cardId, pg.grade, days], queryFn: () => api.priceHistory(cardId, { grade_key: pg.grade, days }) });
  const { data, series, cur } = useMemo(() => {
    const byDate: Record<string, any> = {};
    const names = new Set<string>();
    let cur = "EUR";
    (hist.data ?? []).forEach((p: any) => {
      if (p.market_base == null) return;
      cur = p.base_currency;
      // One line per source+kind (+variant when the source prices variants separately).
      const k = [p.source, p.kind, p.variant].filter(Boolean).join(":");
      names.add(k);
      (byDate[p.observed_on] ??= { d: p.observed_on })[k] = p.market_base / 100;
    });
    return { data: Object.values(byDate).sort((a: any, b: any) => a.d.localeCompare(b.d)), series: [...names].sort(), cur };
  }, [hist.data]);
  const sources = [...new Set(series.map((k) => k.split(":")[0]))];
  const hasAsk = series.some((k) => k.split(":")[1] === "ask");
  const shown = series.filter((k) => !off.has(k.split(":")[0]) && (ask || k.split(":")[1] !== "ask"));
  const toggle = (s: string) => setOff((o) => { const n = new Set(o); n.has(s) ? n.delete(s) : n.add(s); return n; });
  const points = data.length;
  const only = points === 1 ? data[0] : null;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <GradeSelector pg={pg} />
        <SegmentedControl label="Range" value={range} onChange={setRange} options={RANGES.map(([r]) => ({ value: r, label: r }))} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {sources.map((s) => <Chip key={s} active={!off.has(s)} onClick={() => toggle(s)}><SourceDot source={s} /></Chip>)}
        {hasAsk && <Checkbox label="Show ask prices" checked={ask} onChange={(e) => setAsk(e.target.checked)} />}
      </div>
      {hist.isLoading ? <p className="text-sm text-muted">Loading…</p>
        : series.length === 0 ? <p className="text-sm text-muted">No price history for {gradeLabel(pg.grade)} yet. Each fetch adds a point.</p>
        : <>
          <div className="h-64 text-muted"><ResponsiveContainer><LineChart data={data} margin={{ left: 8, right: 16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.2} />
            <XAxis dataKey="d" tick={{ fill: "currentColor", fontSize: 11 }} stroke="currentColor" strokeOpacity={0.3} minTickGap={32} />
            <YAxis width={64} tick={{ fill: "currentColor", fontSize: 11 }} stroke="currentColor" strokeOpacity={0.3} tickFormatter={(v) => money(Math.round(v * 100), cur)} domain={["auto", "auto"]} />
            <Tooltip formatter={(v: any, n: any) => [money(Math.round(v * 100), cur), seriesName(n)]} contentStyle={{ background: "rgb(var(--surface))", border: "1px solid rgb(var(--line))", borderRadius: 8, color: "rgb(var(--fg))" }} />
            <Legend formatter={seriesName} />
            {shown.map((k) => { const [src, kind] = k.split(":"); return (
              <Line key={k} dataKey={k} stroke={SOURCE_COLOR[src] ?? "rgb(var(--muted))"} strokeDasharray={DASH[kind]} strokeWidth={2}
                dot={{ r: points < 20 ? 4 : 0 }} activeDot={{ r: 6 }} connectNulls isAnimationActive={false} />); })}
          </LineChart></ResponsiveContainer></div>
          <p className="text-xs text-muted">
            {only ? `One point so far (${only.d}). ` : `${points} points. `}History fills in with each price fetch. Values in {cur} (today's FX). Solid = sold, dashed = market.</p>
        </>}
    </div>);
}
