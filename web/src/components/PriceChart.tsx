import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../lib/api";
import { SOURCE_COLOR } from "../lib/colors";

const DASH: Record<string, string | undefined> = { sold: undefined, market: "5 4", ask: "2 3" };

export default function PriceChart({ cardId }: { cardId: string }) {
  const [grade, setGrade] = useState("raw");
  const [off, setOff] = useState<Set<string>>(new Set());
  const matrix = useQuery({ queryKey: ["matrix", cardId], queryFn: () => api.priceMatrix(cardId) });
  const grades: string[] = matrix.data?.grades ?? ["raw"];
  const hist = useQuery({ queryKey: ["hist", cardId, grade], queryFn: () => api.priceHistory(cardId, { grade_key: grade }) });
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
  const shown = series.filter((k) => !off.has(k.split(":")[0]));
  const toggle = (s: string) => setOff((o) => { const n = new Set(o); n.has(s) ? n.delete(s) : n.add(s); return n; });
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3 text-sm">
        <label>Grade <select className="input" value={grade} onChange={(e) => setGrade(e.target.value)}>{grades.map((g) => <option key={g}>{g}</option>)}</select></label>
        {sources.map((s) => (
          <label key={s} className="flex items-center gap-1" style={{ color: SOURCE_COLOR[s] }}>
            <input type="checkbox" checked={!off.has(s)} onChange={() => toggle(s)} />{s}</label>))}
      </div>
      {hist.isLoading ? <p className="text-sm opacity-70">Loading…</p>
        : series.length === 0 ? <p className="text-sm opacity-70">No price history for {grade} yet.</p>
        : <>
          <div className="h-64"><ResponsiveContainer><LineChart data={data} margin={{ left: 8, right: 16 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis dataKey="d" /><YAxis width={64} tickFormatter={(v) => money(Math.round(v * 100), cur)} domain={["auto", "auto"]} />
            <Tooltip formatter={(v: any, n: any) => [money(Math.round(v * 100), cur), n]} /><Legend />
            {shown.map((k) => { const [src, kind] = k.split(":"); return (
              <Line key={k} dataKey={k} stroke={SOURCE_COLOR[src] ?? "#64748b"} strokeDasharray={DASH[kind]} strokeWidth={2}
                dot={{ r: 4 }} activeDot={{ r: 6 }} connectNulls isAnimationActive={false} />); })}
          </LineChart></ResponsiveContainer></div>
          {data.length < 2 && <p className="mt-1 text-sm opacity-70">Only one data point so far — history builds with each price refresh.</p>}
          <p className="mt-1 text-xs opacity-60">Values in {cur} (today's FX). Solid = sold, dashed = market.</p>
        </>}
    </div>
  );
}
