import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, money } from "../lib/api";

export default function Search() {
  const [sp, setSp] = useSearchParams();
  const [text, setText] = useState(sp.get("q") ?? "");
  const set = (k: string, v: string) => {
    const n = new URLSearchParams(sp);
    v ? n.set(k, v) : n.delete(k);
    if (k !== "page") n.delete("page");
    setSp(n, { replace: true });
  };
  // Debounce typing into the URL-synced `q` param.
  useEffect(() => { const t = setTimeout(() => set("q", text), 300); return () => clearTimeout(t); }, [text]);

  const params = Object.fromEntries(sp.entries());
  const filters = useQuery({ queryKey: ["filters"], queryFn: api.filters });
  const sets = useQuery({ queryKey: ["sets"], queryFn: () => api.sets() });
  const cards = useQuery({ queryKey: ["cards", params], queryFn: () => api.cards({
    ...params, price_min: params.price_min ? +params.price_min * 100 : undefined,
    price_max: params.price_max ? +params.price_max * 100 : undefined }) });
  const page = +(sp.get("page") ?? 1);
  const pages = cards.data ? Math.ceil(cards.data.total / cards.data.page_size) : 1;
  const sel = (k: string, label: string, opts: { v: string; l: string }[]) => (
    <label className="block text-sm">{label}
      <select className="input mt-1 w-full" value={sp.get(k) ?? ""} onChange={(e) => set(k, e.target.value)}>
        <option value="">All</option>{opts.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
      </select></label>);

  return (
    <div className="grid gap-4 md:grid-cols-[220px_1fr]">
      <aside className="card space-y-3 self-start">
        {sel("set", "Set", (sets.data ?? []).map((s: any) => ({ v: s.external_id, l: s.name })))}
        {sel("type", "Type", (filters.data?.types ?? []).map((t: string) => ({ v: t, l: t })))}
        {sel("rarity", "Rarity", (filters.data?.rarities ?? []).map((t: string) => ({ v: t, l: t })))}
        {sel("supertype", "Supertype", (filters.data?.supertypes ?? []).map((t: string) => ({ v: t, l: t })))}
        {sel("sort", "Sort", [{ v: "name", l: "Name" }, { v: "price_desc", l: "Price high→low" }, { v: "price_asc", l: "Price low→high" }])}
        <div className="flex gap-2">
          <input className="input w-1/2" placeholder="min €" defaultValue={sp.get("price_min") ?? ""} onBlur={(e) => set("price_min", e.target.value)} />
          <input className="input w-1/2" placeholder="max €" defaultValue={sp.get("price_max") ?? ""} onBlur={(e) => set("price_max", e.target.value)} />
        </div>
        <label className="block text-sm">Has price
          <select className="input mt-1 w-full" value={sp.get("has_price") ?? ""} onChange={(e) => set("has_price", e.target.value)}>
            <option value="">Any</option><option value="true">Yes</option><option value="false">No</option>
          </select></label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={sp.get("owned") === "true"} onChange={(e) => set("owned", e.target.checked ? "true" : "")} />Owned only</label>
      </aside>
      <main>
        <input className="input mb-3 w-full text-lg" autoFocus placeholder="Search name, set, number (4/102), text…" value={text} onChange={(e) => setText(e.target.value)} />
        {cards.isLoading && <p>Loading…</p>}
        {cards.error && <p className="text-red-500">{String(cards.error)}</p>}
        {cards.data && cards.data.total === 0 && <p className="opacity-70">No cards. Import a set in Settings.</p>}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {cards.data?.items.map((c: any) => (
            <Link key={c.id} to={`/cards/${encodeURIComponent(c.id)}`} className="card relative block hover:ring-2 hover:ring-indigo-500">
              {c.owned_qty > 0 && <span className="absolute right-2 top-2 rounded bg-emerald-600 px-1.5 text-xs text-white">×{c.owned_qty}</span>}
              <img src={c.images?.small} alt={c.name} loading="lazy" className="mx-auto h-48" />
              <div className="mt-2 text-sm font-medium">{c.name}</div>
              <div className="text-xs opacity-70">{c.set?.name} · {c.number}</div>
              {c.price_base == null
                ? <div className="text-sm opacity-50" title="No source has data for this card yet">no price</div>
                : <div className="text-sm">{money(c.price_base)}</div>}
            </Link>))}
        </div>
        {cards.data && <div className="mt-4 flex items-center gap-3">
          <button className="btn-ghost" disabled={page <= 1} onClick={() => set("page", String(page - 1))}>Prev</button>
          <span className="text-sm">Page {page} / {pages} · {cards.data.total} cards</span>
          <button className="btn-ghost" disabled={page >= pages} onClick={() => set("page", String(page + 1))}>Next</button>
        </div>}
      </main>
    </div>
  );
}
