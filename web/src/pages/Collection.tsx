import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, money } from "../lib/api";

export default function Collection() {
  const [f, setF] = useState({ q: "", graded: "", language: "", condition: "", sort: "added" });
  const sum = useQuery({ queryKey: ["collection", "summary"], queryFn: api.collectionSummary });
  const list = useQuery({ queryKey: ["collection", f], queryFn: () => api.collection(f) });
  const s = sum.data;
  const tile = (l: string, v: string, cls = "") => <div className="card"><div className="text-xs opacity-70">{l}</div><div className={`text-xl font-semibold ${cls}`}>{v}</div></div>;
  return (
    <div className="space-y-4">
      {s && <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {tile("Cards", `${s.cards} (${s.distinct} distinct)`)}{tile("Value", money(s.value))}{tile("Cost", money(s.cost))}
        {tile("P/L", s.pl == null ? "—" : money(s.pl), s.pl == null ? "" : s.pl >= 0 ? "text-emerald-600" : "text-red-500")}
        {tile("Unpriced / estimated", `${s.unpriced} / ${s.estimated}`)}</div>}
      <div className="flex flex-wrap gap-2">
        <input className="input" placeholder="Search owned…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
        <select className="input" value={f.graded} onChange={(e) => setF({ ...f, graded: e.target.value })}><option value="">Raw+graded</option><option value="false">Raw</option><option value="true">Graded</option></select>
        <select className="input" value={f.condition} onChange={(e) => setF({ ...f, condition: e.target.value })}><option value="">Any cond.</option>{["NM", "LP", "MP", "HP", "DMG"].map((c) => <option key={c}>{c}</option>)}</select>
        <select className="input" value={f.sort} onChange={(e) => setF({ ...f, sort: e.target.value })}><option value="added">Newest</option><option value="value">Value</option><option value="name">Name</option></select>
      </div>
      {list.data?.items.length === 0 && <p className="opacity-70">Nothing here. Add cards from the Search page.</p>}
      <table className="w-full text-sm"><thead><tr className="text-left opacity-70"><th></th><th>Card</th><th>Set</th><th>Details</th><th>Qty</th><th>Value</th><th>Cost</th></tr></thead><tbody>
        {list.data?.items.map((i: any) => (
          <tr key={i.id} className="border-t dark:border-slate-700">
            <td><img src={i.card?.images?.small} className="h-12" /></td>
            <td><Link className="hover:underline" to={`/cards/${encodeURIComponent(i.card_id)}`}>{i.card?.name}</Link></td>
            <td>{i.card?.set?.name} #{i.card?.number}</td>
            <td>{i.variant ? `${i.variant} · ` : ""}{i.language.toUpperCase()} · {i.grading ? `${i.grading.company} ${i.grading.grade}` : i.condition}</td>
            <td>{i.quantity}</td>
            <td>{money(i.value)}{i.estimated && <span title="Estimated: raw price used for graded / variant fallback"> ≈</span>}</td>
            <td>{money(i.cost)}</td></tr>))}
      </tbody></table>
    </div>
  );
}
