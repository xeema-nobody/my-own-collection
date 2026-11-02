import { QueryError } from "../components/QueryState";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Heart, Search as SearchIcon, X } from "lucide-react";
import { api, money } from "../lib/api";
import { Badge, Button, Card, Chip, Combobox, cx, EmptyState, Field, Input, Select, Skeleton } from "../components/ui";
import { activeFilters, SORT_OPTIONS, withoutKeys } from "../lib/searchFilters";

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
  const setName = (id: string) => (sets.data ?? []).find((s: any) => s.external_id === id)?.name as string | undefined;
  const chips = activeFilters(sp, setName);
  const curSet = (sets.data ?? []).find((s: any) => s.external_id === sp.get("set"));
  const page = +(sp.get("page") ?? 1);
  const pages = cards.data ? Math.ceil(cards.data.total / cards.data.page_size) : 1;
  const sel = (k: string, label: string, opts: { v: string; l: string }[], all = "All") => (
    <Field label={label}>
      <Select aria-label={label} value={sp.get(k) ?? ""} onChange={(v) => set(k, v)} allLabel={all} options={opts.map((o) => ({ value: o.v, label: o.l }))} />
    </Field>);

  return (
    <div className={cx("grid gap-6 md:grid-cols-[240px_1fr]", selected.size > 0 && "pb-16")}>
      <aside className="space-y-3 self-start rounded-lg bg-surface p-4 shadow-card md:sticky md:top-20">
        <Field label="Set">
          <Combobox aria-label="Set" cacheKey="search-sets" value={sp.get("set") ?? ""} selectedLabel={setName(sp.get("set") ?? "")}
            placeholder="All sets" onChange={(v) => set("set", v)}
            fetchPage={async (q, pg) => {
              const hit = (sets.data ?? []).filter((s: any) => `${s.name} ${s.series ?? ""} ${s.external_id}`.toLowerCase().includes(q.toLowerCase()));
              return { options: hit.slice(0, pg * 40).map((s: any) => ({ value: s.external_id, label: `${s.name} · ${s.series ?? ""}` })), more: hit.length > pg * 40 };
            }} />
        </Field>
        {sel("type", "Type", (filters.data?.types ?? []).map((t: string) => ({ v: t, l: t })))}
        {sel("rarity", "Rarity", (filters.data?.rarities ?? []).map((t: string) => ({ v: t, l: t })))}
        {sel("supertype", "Supertype", (filters.data?.supertypes ?? []).map((t: string) => ({ v: t, l: t })))}
        <div className="flex gap-2">
          <Input className="w-1/2" placeholder="min €" aria-label="Min price" defaultValue={sp.get("price_min") ?? ""} onBlur={(e) => set("price_min", e.target.value)} />
          <Input className="w-1/2" placeholder="max €" aria-label="Max price" defaultValue={sp.get("price_max") ?? ""} onBlur={(e) => set("price_max", e.target.value)} />
        </div>
        {sel("has_price", "Has price", [{ v: "true", l: "Yes" }, { v: "false", l: "No" }], "Any")}
        <Chip active={sp.get("owned") === "true"} onClick={() => set("owned", sp.get("owned") === "true" ? "" : "true")}>Owned only</Chip>
      </aside>
      <main>
        <div className="relative mb-4">
          <SearchIcon size={18} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <Input className="py-2.5 pl-10 text-base" autoFocus placeholder="Search name, set, number (4/102), text…" value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        {curSet && (
          <Card className="mb-4 flex items-center gap-4">
            {curSet.logo_url && <img src={curSet.logo_url} alt={curSet.name} className="h-12 max-w-40 object-contain" />}
            <div className="min-w-0 text-sm">
              <div className="truncate font-semibold">{curSet.name}</div>
              <div className="text-muted">{curSet.series} · {curSet.printed_total ?? curSet.total} printed · {String(curSet.release_date ?? "").slice(0, 10)}</div>
            </div>
          </Card>)}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {chips.map((f) => (
            <Chip key={f.id} active onClick={() => setSp(withoutKeys(sp, f.keys), { replace: true })} aria-label={`Remove filter ${f.label}`}>
              {f.label} <X size={12} className="ml-0.5 inline" />
            </Chip>))}
          {chips.length > 1 && <Button variant="ghost" size="sm" onClick={() => setSp(withoutKeys(sp, chips.flatMap((f) => f.keys)), { replace: true })}>Clear all</Button>}
          <span className="num ml-auto text-sm text-muted">{cards.data ? `${cards.data.total} cards` : ""}</span>
          <div className="w-48">
            <Select aria-label="Sort" value={sp.get("sort") || "release"} onChange={(v) => set("sort", v === "release" ? "" : v)} options={SORT_OPTIONS} />
          </div>
        </div>
        {cards.isLoading && <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-5 2xl:grid-cols-6">{Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="h-72" />)}</div>}
        <QueryError q={cards} label="Search" />
        {cards.data && cards.data.total === 0 && <EmptyState title="No cards found">Import a set in Settings, or relax the filters.</EmptyState>}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-5 2xl:grid-cols-6">
          {cards.data?.items.map((c: any) => (
            <div key={c.id} className="group relative">
              <input type="checkbox" className="absolute left-3 top-3 z-10 h-4 w-4 accent-[rgb(var(--accent))]" aria-label={`Select ${c.name} for price fetch`} title="Select for price fetch"
                checked={selected.has(c.id)} onChange={() => pick(c.id)} />
              <Link to={`/cards/${encodeURIComponent(c.id)}`} className="block rounded-lg bg-surface p-3 shadow-card transition hover:ring-2 hover:ring-accent/60">
                <div className="absolute right-3 top-3 flex gap-1">
                  {c.wished && <Badge tone="warn" title="On your wishlist" aria-label="On wishlist"><Heart size={11} className="fill-current" /></Badge>}
                  {c.owned_qty > 0 && <Badge tone="accent" className="num">×{c.owned_qty}</Badge>}
                </div>
                <img src={c.images?.small} alt={c.name} loading="lazy" className="mx-auto h-52 object-contain" />
                <div className="mt-3 truncate text-sm font-medium">{c.name}</div>
                <div className="flex items-center gap-1 truncate text-xs text-muted">
                  {c.set?.symbol_url && <img src={c.set.symbol_url} alt="" loading="lazy" className="h-3.5 w-3.5 shrink-0 object-contain" />}
                  <span className="truncate">{c.set?.name} · {c.number}</span></div>
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
      {(selected.size > 0 || fetchSel.isSuccess || fetchSel.error) && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 backdrop-blur">
          <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-3 px-4 py-3 text-sm">
            {selected.size > 0 && <>
              <span className="num font-medium">{selected.size} selected</span>
              <Button disabled={fetchSel.isPending} onClick={() => fetchSel.mutate()}>Fetch prices</Button>
              <Button variant="secondary" onClick={() => setSelected((p) => new Set([...p, ...(cards.data?.items ?? []).map((c: any) => c.id)]))}>Select page</Button>
              <Button variant="ghost" onClick={() => setSelected(new Set())}>Clear</Button></>}
            {fetchSel.isSuccess && selected.size === 0 && <span className="text-ok">Fetch started for {fetchSel.data.cards} cards – progress in <Link className="underline" to="/settings">Settings</Link>.</span>}
            {fetchSel.error && <span className="text-danger">{String(fetchSel.error)}</span>}
          </div>
        </div>)}
    </div>
  );
}
