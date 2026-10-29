import { QueryError } from "../components/QueryState";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Search as SearchIcon } from "lucide-react";
import { api, money } from "../lib/api";
import { Badge, Button, Card, Checkbox, EmptyState, Field, Input, Select, Skeleton } from "../components/ui";

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
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const fetchSel = useMutation({
    mutationFn: () => api.fetchPrices({ cards: [...selected] }),
    onSuccess: () => setSelected(new Set()),
  });
  const pick = (id: string) => setSelected((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const page = +(sp.get("page") ?? 1);
  const pages = cards.data ? Math.ceil(cards.data.total / cards.data.page_size) : 1;
  const sel = (k: string, label: string, opts: { v: string; l: string }[], all = "All") => (
    <Field label={label}>
      <Select aria-label={label} value={sp.get(k) ?? ""} onChange={(v) => set(k, v)} allLabel={all} options={opts.map((o) => ({ value: o.v, label: o.l }))} />
    </Field>);

  return (
    <div className="grid gap-6 md:grid-cols-[240px_1fr]">
      <aside className="space-y-3 self-start rounded-lg bg-surface p-4 shadow-card md:sticky md:top-20">
        {sel("set", "Set", (sets.data ?? []).map((s: any) => ({ v: s.external_id, l: s.name })))}
        {sel("type", "Type", (filters.data?.types ?? []).map((t: string) => ({ v: t, l: t })))}
        {sel("rarity", "Rarity", (filters.data?.rarities ?? []).map((t: string) => ({ v: t, l: t })))}
        {sel("supertype", "Supertype", (filters.data?.supertypes ?? []).map((t: string) => ({ v: t, l: t })))}
        <Field label="Sort">
          <Select aria-label="Sort" value={sp.get("sort") ?? ""} onChange={(v) => set("sort", v)} allLabel="Name"
            options={[{ value: "price_desc", label: "Price high→low" }, { value: "price_asc", label: "Price low→high" }]} />
        </Field>
        <div className="flex gap-2">
          <Input className="w-1/2" placeholder="min €" aria-label="Min price" defaultValue={sp.get("price_min") ?? ""} onBlur={(e) => set("price_min", e.target.value)} />
          <Input className="w-1/2" placeholder="max €" aria-label="Max price" defaultValue={sp.get("price_max") ?? ""} onBlur={(e) => set("price_max", e.target.value)} />
        </div>
        {sel("has_price", "Has price", [{ v: "true", l: "Yes" }, { v: "false", l: "No" }], "Any")}
        <Checkbox label="Owned only" checked={sp.get("owned") === "true"} onChange={(e) => set("owned", e.target.checked ? "true" : "")} />
      </aside>
      <main>
        <div className="relative mb-4">
          <SearchIcon size={18} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <Input className="py-2.5 pl-10 text-base" autoFocus placeholder="Search name, set, number (4/102), text…" value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        {(selected.size > 0 || fetchSel.isSuccess || fetchSel.error) && (
          <Card className="mb-4 flex flex-wrap items-center gap-3 text-sm">
            {selected.size > 0 && <>
              <Button disabled={fetchSel.isPending} onClick={() => fetchSel.mutate()}>Fetch prices for {selected.size} selected</Button>
              <Button variant="secondary" onClick={() => setSelected(new Set())}>Clear</Button></>}
            {fetchSel.isSuccess && selected.size === 0 && <span className="text-ok">Fetch started for {fetchSel.data.cards} cards – progress in <Link className="underline" to="/settings">Settings</Link>.</span>}
            {fetchSel.error && <span className="text-danger">{String(fetchSel.error)}</span>}
          </Card>)}
        {cards.isLoading && <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-5 2xl:grid-cols-6">{Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="h-72" />)}</div>}
        <QueryError q={cards} label="Search" />
        {cards.data && cards.data.total === 0 && <EmptyState title="No cards found">Import a set in Settings, or relax the filters.</EmptyState>}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-5 2xl:grid-cols-6">
          {cards.data?.items.map((c: any) => (
            <div key={c.id} className="group relative">
              <input type="checkbox" className="absolute left-3 top-3 z-10 h-4 w-4 accent-[rgb(var(--accent))]" aria-label={`Select ${c.name} for price fetch`} title="Select for price fetch"
                checked={selected.has(c.id)} onChange={() => pick(c.id)} />
              <Link to={`/cards/${encodeURIComponent(c.id)}`} className="block rounded-lg bg-surface p-3 shadow-card transition hover:ring-2 hover:ring-accent/60">
                {c.owned_qty > 0 && <Badge tone="accent" className="num absolute right-3 top-3">×{c.owned_qty}</Badge>}
                <img src={c.images?.small} alt={c.name} loading="lazy" className="mx-auto h-52 object-contain" />
                <div className="mt-3 truncate text-sm font-medium">{c.name}</div>
                <div className="truncate text-xs text-muted">{c.set?.name} · {c.number}</div>
                {c.price_base == null
                  ? <div className="mt-1 text-sm text-muted" title="No source has data for this card yet">no price</div>
                  : <div className="num mt-1 text-sm font-semibold">{money(c.price_base)}</div>}
              </Link></div>))}
        </div>
        {cards.data && <div className="mt-6 flex items-center justify-center gap-3">
          <Button variant="secondary" disabled={page <= 1} onClick={() => set("page", String(page - 1))}>Prev</Button>
          <span className="num text-sm text-muted">Page {page} / {pages} · {cards.data.total} cards</span>
          <Button variant="secondary" disabled={page >= pages} onClick={() => set("page", String(page + 1))}>Next</Button>
        </div>}
      </main>
    </div>
  );
}
