import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, money } from "../lib/api";
import { KIND_CLASS } from "../lib/colors";
import SourceCompare from "../components/SourceCompare";

// Why a value is not an exact-grade price; "" = exact.
function whyEstimated(i: any): string {
  const why = [] as string[];
  if (i.match === "bucket") why.push(`company-agnostic ${i.grade_key_used} price, not ${i.grading?.company} ${i.grading?.grade}`);
  else if (i.match === "lower") why.push(`no ${i.grading?.company} ${i.grading?.grade} price, using lower grade ${i.grade_key_used}`);
  else if (i.match === "raw_fallback") why.push("no graded price, using raw price");
  if (i.estimated && i.match === "exact") why.push("variant price missing, used another variant");
  return why.join("; ");
}

function Value({ i, open, toggle }: { i: any; open: boolean; toggle: () => void }) {
  if (i.value == null) return <span className="opacity-70" title="No price for this grade">no price</span>;
  const why = whyEstimated(i);
  const far = (i.spread?.outliers ?? []).length > 0;
  return <span title={i.headline_rule ?? ""}>{money(i.value)}{why && <span title={why}> ≈</span>}
    <span className={`ml-1 rounded px-1 text-xs ${KIND_CLASS[i.price_kind] ?? ""}`}>{i.price_kind}</span>
    <span className="ml-1 text-xs opacity-70">{i.source}{i.thin && i.sample_size ? ` · only ${i.sample_size} sold` : ""}</span>
    {why && <div className="text-xs text-amber-600 dark:text-amber-400">{why}</div>}
    <button className="btn-ghost ml-1 text-xs" onClick={toggle} aria-expanded={open}>{open ? "hide sources" : `compare ${Object.keys(i.sources ?? {}).length} sources`}{far ? " ⚠" : ""}</button></span>;
}

export default function Collection() {
  const [f, setF] = useState({ q: "", graded: "", language: "", condition: "", sort: "added" });
  const [open, setOpen] = useState<Record<string, boolean>>({});
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
          <Fragment key={i.id}><tr className="border-t dark:border-slate-700">
            <td><img src={i.card?.images?.small} className="h-12" /></td>
            <td><Link className="hover:underline" to={`/cards/${encodeURIComponent(i.card_id)}`}>{i.card?.name}</Link></td>
            <td>{i.card?.set?.name} #{i.card?.number}</td>
            <td>{i.variant ? `${i.variant} · ` : ""}{i.language.toUpperCase()} · {i.grading ? `${i.grading.company} ${i.grading.grade}` : i.condition}</td>
            <td>{i.quantity}</td>
            <td><Value i={i} open={!!open[i.id]} toggle={() => setOpen((o) => ({ ...o, [i.id]: !o[i.id] }))} /></td>
            <td>{money(i.cost)}</td></tr>
            {open[i.id] && <tr><td></td><td colSpan={6} className="pb-3"><SourceCompare row={i} /></td></tr>}</Fragment>))}
      </tbody></table>
    </div>
  );
}
