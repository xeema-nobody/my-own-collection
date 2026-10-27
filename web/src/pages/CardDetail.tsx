import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, money } from "../lib/api";
import { SOURCE_COLOR } from "../lib/colors";

const CONDITIONS = ["NM", "LP", "MP", "HP", "DMG"];
const LANGS = ["en", "ja", "es", "it", "fr", "de", "pt", "ko", "zh"];
const GRADERS = ["PSA", "BGS", "CGC", "SGC", "ACE", "OTHER"];

export default function CardDetail() {
  const id = decodeURIComponent(useParams().id!);
  const qc = useQueryClient();
  const card = useQuery({ queryKey: ["card", id], queryFn: () => api.card(id) });
  const hist = useQuery({ queryKey: ["hist", id], queryFn: () => api.priceHistory(id) });
  const [f, setF] = useState({ variant: "", language: "en", graded: false, condition: "NM", company: "PSA", grade: "9", cert: "", qty: "1", price: "", notes: "" });
  const add = useMutation({
    mutationFn: () => api.addToCollection({
      card_id: id, variant: f.variant || card.data.variants[0], language: f.language,
      condition: f.graded ? null : f.condition,
      grading: f.graded ? { company: f.company, grade: +f.grade, cert_number: f.cert || null } : null,
      quantity: +f.qty, notes: f.notes || null,
      acquired: f.price ? { price: Math.round(+f.price * 100), currency: "EUR" } : null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["card", id] }); qc.invalidateQueries({ queryKey: ["collection"] }); },
  });
  const dec = useMutation({
    mutationFn: ({ sid, del }: { sid: string; del?: boolean }) => del ? api.deleteItem(sid) : api.removeFromCollection(sid, 1),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["card", id] }),
  });
  const inc = useMutation({ mutationFn: (s: any) => api.addToCollection({ card_id: id, variant: s.variant, language: s.language, condition: s.condition, grading: s.grading, quantity: 1 }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["card", id] }) });

  if (card.isLoading) return <p>Loading…</p>;
  if (card.error) return <p className="text-red-500">{String(card.error)}</p>;
  const c = card.data;
  // Pivot history rows into one series per source (market value, native currency).
  const byDate: Record<string, any> = {};
  (hist.data ?? []).forEach((p: any) => { const d = p.as_of.slice(0, 10); (byDate[d] ??= { d })[p.source + ":" + p.variant] = p.market / 100; });
  const series = Object.keys(Object.assign({}, ...Object.values(byDate))).filter((k) => k !== "d");
  const field = (label: string, el: React.ReactNode) => <label className="block text-sm">{label}{el}</label>;
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  return (
    <div className="grid gap-6 md:grid-cols-[300px_1fr]">
      <img src={c.images?.large} alt={c.name} className="w-full max-w-xs" />
      <div className="space-y-4">
        <div><h1 className="text-2xl font-bold">{c.name}</h1>
          <p className="opacity-70">{c.set?.name} · #{c.number}/{c.set?.printed_total} · {c.rarity} · {c.types?.join(", ")}</p>
          {c.flavor_text && <p className="mt-1 text-sm italic">{c.flavor_text}</p>}</div>

        <section className="card"><h2 className="mb-2 font-semibold">Prices <span className="rounded bg-slate-200 px-1.5 text-xs dark:bg-slate-700">Market price (aggregate)</span></h2>
          <table className="w-full text-sm"><thead><tr className="text-left opacity-70"><th>Source</th><th>Variant</th><th>Low</th><th>Avg</th><th>High</th><th>Market/Trend</th><th>As of</th></tr></thead><tbody>
            {Object.entries(c.latest_price ?? {}).flatMap(([src, vs]: any) => Object.entries(vs).map(([v, p]: any) => (
              <tr key={src + v}><td style={{ color: SOURCE_COLOR[src] }}>{src}</td><td>{v}</td>
                <td>{money(p.low, p.currency)}</td><td>{money(p.avg, p.currency)}</td><td>{money(p.high, p.currency)}</td><td>{money(p.market, p.currency)}</td><td>{p.as_of?.slice(0, 10)}</td></tr>)))}
          </tbody></table>
          {(c.sales_stats ?? []).map((s: any, i: number) => <p key={i} className="mt-2 text-sm">Sold ({s.count} sales, {s.source}, {s.grade_key}): min {money(s.min, s.currency)} · avg {money(s.avg, s.currency)} · max {money(s.max, s.currency)}</p>)}
        </section>

        {series.length > 0 && Object.keys(byDate).length > 1 && <section className="card h-64"><ResponsiveContainer><LineChart data={Object.values(byDate).sort((a: any, b: any) => a.d.localeCompare(b.d))}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} /><XAxis dataKey="d" /><YAxis /><Tooltip /><Legend />
          {series.map((k) => <Line key={k} dataKey={k} stroke={SOURCE_COLOR[k.split(":")[0]]} dot={false} connectNulls />)}</LineChart></ResponsiveContainer></section>}

        <section className="card"><h2 className="mb-2 font-semibold">Owned</h2>
          {c.owned.length === 0 && <p className="text-sm opacity-70">None yet.</p>}
          {c.owned.map((s: any) => (
            <div key={s.id} className="flex items-center gap-2 border-b py-1 text-sm last:border-0 dark:border-slate-700">
              <span className="flex-1">{s.variant} · {s.language.toUpperCase()} · {s.grading ? `${s.grading.company} ${s.grading.grade}` : s.condition}</span>
              <button className="btn-ghost" onClick={() => dec.mutate({ sid: s.id })}>−</button>
              <span className="w-6 text-center">{s.quantity}</span>
              <button className="btn-ghost" disabled={!!s.grading?.cert_number} onClick={() => inc.mutate(s)}>+</button>
              <button className="btn-ghost" onClick={() => dec.mutate({ sid: s.id, del: true })}>Remove</button>
            </div>))}
        </section>

        <section className="card"><h2 className="mb-2 font-semibold">Add to collection</h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {field("Variant", <select className="input w-full" value={f.variant} onChange={set("variant")}>{c.variants.map((v: string) => <option key={v}>{v}</option>)}</select>)}
            {field("Language", <select className="input w-full" value={f.language} onChange={set("language")}>{LANGS.map((v) => <option key={v}>{v}</option>)}</select>)}
            <label className="flex items-end gap-2 text-sm"><input type="checkbox" checked={f.graded} onChange={set("graded")} />Graded</label>
            {!f.graded ? field("Condition", <select className="input w-full" value={f.condition} onChange={set("condition")}>{CONDITIONS.map((v) => <option key={v}>{v}</option>)}</select>)
              : <>{field("Grader", <select className="input w-full" value={f.company} onChange={set("company")}>{GRADERS.map((v) => <option key={v}>{v}</option>)}</select>)}
                {field("Grade", <input className="input w-full" type="number" step="0.5" min="1" max="10" value={f.grade} onChange={set("grade")} />)}
                {field("Cert #", <input className="input w-full" value={f.cert} onChange={set("cert")} />)}</>}
            {field("Quantity", <input className="input w-full" type="number" min="1" value={f.qty} onChange={set("qty")} />)}
            {field("Price paid (€)", <input className="input w-full" type="number" step="0.01" value={f.price} onChange={set("price")} />)}
            {field("Notes", <input className="input w-full" value={f.notes} onChange={set("notes")} />)}
          </div>
          <button className="btn mt-3" disabled={add.isPending} onClick={() => add.mutate()}>Add</button>
          {add.error && <span className="ml-3 text-sm text-red-500">{String(add.error)}</span>}
          {add.isSuccess && <span className="ml-3 text-sm text-emerald-600">Added</span>}
        </section>
      </div>
    </div>
  );
}
