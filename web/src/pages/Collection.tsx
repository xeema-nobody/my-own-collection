import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, ChevronRight, TriangleAlert } from "lucide-react";
import { api, money, ago } from "../lib/api";
import AcquiredForm, { ACQ_TYPES, AcqBadge, acqLabel } from "../components/AcquiredForm";
import { QueryError } from "../components/QueryState";
import SourceCompare from "../components/SourceCompare";
import BulkFetch, { fetchErrorText } from "../components/BulkFetch";
import FetcherBadge from "../components/FetcherBadge";
import ValueChart from "../components/ValueChart";
import { usePriceFetchJob } from "../lib/fetchJob";
import { Badge, Button, Card, Checkbox, Drawer, EmptyState, Input, Kpi, Pagination, Select, Skeleton, SortTh, Table, THead, Td, Th, Tr } from "../components/ui";

// Why a value is not an exact-grade price; "" = exact.
function whyEstimated(i: any): string {
  const why = [] as string[];
  if (i.match === "bucket") why.push(`company-agnostic ${i.grade_key_used} price, not ${i.grading?.company} ${i.grading?.grade}`);
  else if (i.match === "lower") why.push(`no ${i.grading?.company} ${i.grading?.grade} price, using lower grade ${i.grade_key_used}`);
  else if (i.match === "needs_graded_price") why.push("no graded price yet, not counted");
  if (i.estimated && i.match === "exact") why.push("variant price missing, used another variant");
  return why.join("; ");
}

const KIND_TONE = { sold: "ok", market: "neutral", ask: "warn" } as const;
const DEFAULTS = { q: "", graded: "", language: "", condition: "", needs_price: "", acquisition: "", cost_missing: "", sort: "added", order: "", page: "1", size: "50" };
type Params = typeof DEFAULTS;

const COLS: { key: string; label: string; num?: boolean }[] = [
  { key: "name", label: "Card" }, { key: "set", label: "Set" }, { key: "", label: "Details" },
  { key: "qty", label: "Qty", num: true }, { key: "value", label: "Value", num: true },
  { key: "cost", label: "Cost", num: true }, { key: "pl", label: "P/L", num: true },
];
const DEFAULT_DESC = ["added", "value", "cost", "pl", "qty"];

function Value({ i }: { i: any }) {
  if (i.needs_price) return <Badge tone="warn" title="A slab is not worth its raw copy, so it is left out of totals until a graded price is fetched">needs price</Badge>;
  if (i.value == null) return <span className="text-muted" title="No price for this grade">no price</span>;
  const why = whyEstimated(i);
  return <span className="inline-flex items-center justify-end gap-1.5" title={i.headline_rule ?? ""}>
    {why && <span title={why} className="text-warn">≈</span>}<span className="font-semibold">{money(i.value)}</span>
    <Badge tone={KIND_TONE[i.price_kind as keyof typeof KIND_TONE] ?? "neutral"}>{i.price_kind}</Badge></span>;
}

const detail = (i: any) => `${i.variant ? `${i.variant} · ` : ""}${i.language.toUpperCase()} · ${i.grading ? `${i.grading.company} ${i.grading.grade}` : i.condition}`;

const fmtAcq = (a: any) => a ? `${acqLabel(a.type)} · ${a.price == null ? "no price" : money(a.price, a.currency)}${a.date ? ` · ${a.date}` : ""}${a.source ? ` · ${a.source}` : ""}` : "nothing";

/** Edit cost + acquisition of one stack, with the edit log (each row can be restored). */
function CostSection({ i }: { i: any }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const hist = useQuery({ queryKey: ["stack-history", i.id], queryFn: () => api.stackHistory(i.id) });
  const done = () => { qc.invalidateQueries({ queryKey: ["collection"] }); qc.invalidateQueries({ queryKey: ["stack-history", i.id] }); };
  const save = useMutation({ mutationFn: (acquired: any) => api.patchStack(i.id, { acquired }), onSuccess: () => { done(); setOpen(false); } });
  const restore = useMutation({ mutationFn: (eid: string) => api.restoreEdit(i.id, eid), onSuccess: done });
  const a = i.acquired;
  return (
    <section className="space-y-2 border-t border-line pt-3 text-sm" aria-label="Cost and acquisition">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium">Cost &amp; acquisition</h3>
        <Button variant="secondary" size="sm" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Cancel" : "Edit cost"}</Button>
      </div>
      <div className="text-muted">{a ? <>{fmtAcq(a)} <span className="num">(×{i.quantity} = {money(i.cost)})</span></> : "No cost recorded."}</div>
      {open && <AcquiredForm key={`${i.id}-${JSON.stringify(a)}`} initial={a} qty={i.quantity} busy={save.isPending} onSubmit={(p) => save.mutate(p)} />}
      {save.error && <div role="alert" className="text-danger">{String((save.error as Error).message)}</div>}
      {(hist.data?.length ?? 0) > 0 && <details className="text-xs text-muted">
        <summary className="cursor-pointer">Edit history ({hist.data!.length})</summary>
        <ul className="mt-1 divide-y divide-line">
          {hist.data!.map((e) => <li key={e.id} className="flex flex-wrap items-center gap-2 py-1">
            <span className="w-16">{ago(e.at)}</span><Badge>{e.action}</Badge>
            <span className="min-w-0 flex-1">{fmtAcq(e.before)} → {fmtAcq(e.after)}</span>
            <Button variant="ghost" size="sm" disabled={restore.isPending} aria-label={`Restore previous value from ${e.action} ${ago(e.at)}`} onClick={() => restore.mutate(e.id)}>Restore previous</Button>
          </li>)}
        </ul></details>}
    </section>);
}

function Details({ i }: { i: any }) {
  const why = whyEstimated(i);
  const qc = useQueryClient();
  const fetchStack = useMutation({ mutationFn: () => api.fetchPrices({ mode: "stack", stack_id: i.id }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["jobs"] }) });
  return (
    <div className="space-y-4">
      <div className="flex gap-4">
        {i.card?.images?.small && <img src={i.card.images.small} alt="" className="h-36 rounded" />}
        <div className="space-y-1 text-sm">
          <div className="text-muted">{i.card?.set?.name} #{i.card?.number} · {detail(i)} · ×{i.quantity}</div>
          <div className="num">Value <span className="text-lg font-semibold">{i.needs_price ? "not priced" : money(i.value)}</span>
            {i.source && <span className="text-muted"> · {i.source}{i.thin && i.sample_size ? ` · only ${i.sample_size} sold` : ""}</span>}</div>
          <div className="num text-muted">Cost {money(i.cost)}{i.pl != null && <> · P/L <span className={i.pl >= 0 ? "text-ok" : "text-danger"}>{money(i.pl)}</span></>}</div>
          {i.needs_price && i.ref_raw_value != null && <div className="text-muted">Raw copy ≈ {money(i.ref_raw_value)}, not counted.</div>}
          {why && <div className="flex items-start gap-1 text-warn"><TriangleAlert size={14} className="mt-0.5 shrink-0" />{why}</div>}
          <div className="flex gap-2 pt-1">
            <Link to={`/cards/${encodeURIComponent(i.card_id)}`}><Button variant="secondary" size="sm">Open card</Button></Link>
            <Link to={`/alerts?stack=${i.id}`}><Button variant="secondary" size="sm"><Bell size={12} />Create alert</Button></Link>
            <Button variant="secondary" size="sm" disabled={fetchStack.isPending} onClick={() => fetchStack.mutate()}>Fetch prices for this stack</Button>
          </div>
          {fetchStack.error && <div className="text-danger">{fetchErrorText(fetchStack.error)}</div>}
          {fetchStack.isSuccess && <div className="text-muted">Fetch started: progress shows at the top of the page.</div>}
        </div>
      </div>
      <CostSection i={i} />
      <SourceCompare row={i} />
    </div>);
}

export default function Collection() {
  const qc = useQueryClient();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [bulkOpen, setBulkOpen] = useState(false);
  const [sp, setSp] = useSearchParams();
  const f: Params = { ...DEFAULTS, ...Object.fromEntries(sp) };
  const [sel, setSel] = useState<any>(null);
  const set = (patch: Partial<Params>, keepPage = false) => {
    const next = { ...f, ...(keepPage ? {} : { page: "1" }), ...patch };
    setSp(Object.fromEntries(Object.entries(next).filter(([k, v]) => v !== DEFAULTS[k as keyof Params])), { replace: true });
  };
  const sum = useQuery({ queryKey: ["collection", "summary"], queryFn: api.collectionSummary });
  const query = { q: f.q, graded: f.graded, language: f.language, condition: f.condition, needs_price: f.needs_price, acquisition: f.acquisition, cost_missing: f.cost_missing,
    sort: f.sort, order: f.order, page: f.page, page_size: f.size };
  const list = useQuery({ queryKey: ["collection", query], queryFn: () => api.collection(query), placeholderData: (p) => p });
  const s = sum.data;
  const { running } = usePriceFetchJob(() => qc.invalidateQueries({ queryKey: ["collection"] }));
  const fetchMissing = useMutation({ mutationFn: () => api.fetchPrices({ missing: true }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["jobs"] }) });
  const bulk = useMutation({ mutationFn: (acquired: any) => api.bulkAcquired([...picked], acquired),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["collection"] }); qc.invalidateQueries({ queryKey: ["stack-history"] }); } });
  const FILTERS = ["q", "graded", "language", "condition", "needs_price", "acquisition", "cost_missing"] as const;
  const dirty = FILTERS.some((k) => f[k] !== "");
  const dir: "asc" | "desc" = f.order ? (f.order as "asc" | "desc") : DEFAULT_DESC.includes(f.sort) ? "desc" : "asc";
  const sort = (key: string) => key && set(f.sort === key ? { order: dir === "desc" ? "asc" : "desc" } : { sort: key, order: "" });
  const items: any[] = list.data?.items ?? [];
  const cur = sel ? items.find((x) => x.id === sel.id) ?? sel : null;  // refreshed row after an edit
  const allOnPage = items.length > 0 && items.every((x) => picked.has(x.id));
  const toggle = (id: string) => setPicked((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const togglePage = () => setPicked((p) => { const n = new Set(p); items.forEach((x) => allOnPage ? n.delete(x.id) : n.add(x.id)); return n; });

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Collection</h1>
      <QueryError q={sum} label="Summary" />
      {sum.isLoading && <div className="grid grid-cols-2 gap-3 md:grid-cols-5">{[0, 1, 2, 3, 4].map((n) => <Skeleton key={n} className="h-20" />)}</div>}
      {s && <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
        <Kpi label="Cards" value={s.cards} hint={`${s.distinct} distinct`} />
        <Kpi label="Value" value={money(s.value)} />
        <Kpi label="Cost" value={money(s.cost)} hint={s.cost_missing > 0 ? `${s.cost_missing} stack${s.cost_missing === 1 ? "" : "s"} without cost` : undefined} />
        <Kpi label="P/L" value={s.pl == null ? "—" : money(s.pl)} tone={s.pl == null ? undefined : s.pl >= 0 ? "ok" : "danger"}
          hint={s.pl != null && s.cost_basis_cost ? `${s.pl >= 0 ? "+" : ""}${((s.pl / s.cost_basis_cost) * 100).toFixed(1)}% of cost` : undefined} />
        <Kpi label="P/L excl. pulled" value={s.pl_ex_pulled == null ? "—" : money(s.pl_ex_pulled)} tone={s.pl_ex_pulled == null ? undefined : s.pl_ex_pulled >= 0 ? "ok" : "danger"}
          hint={s.pl_ex_pulled != null && s.cost_basis_cost_ex_pulled ? `${s.pl_ex_pulled >= 0 ? "+" : ""}${((s.pl_ex_pulled / s.cost_basis_cost_ex_pulled) * 100).toFixed(1)}% of cost` : undefined} />
        <Kpi label="Needs price / estimated" value={`${s.needs_price} / ${s.estimated}`} />
      </div>}
      {s?.cost_missing > 0 && <p className="text-xs text-muted">P/L counts only stacks with a cost.{" "}
        <button type="button" className="text-accent hover:underline" onClick={() => set({ cost_missing: "true" })}>Show the {s.cost_missing} without cost</button> to fix them in bulk.</p>}
      {s?.needs_price > 0 && <Card className="border-l-2 border-warn text-sm">
        <p>{s.needs_price} graded stack{s.needs_price === 1 ? "" : "s"} without a graded price {s.needs_price === 1 ? "is" : "are"} not counted in Value or P/L
          (their raw copies would add about {money(s.ref_raw_value)}).</p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <Button disabled={!!running || fetchMissing.isPending} onClick={() => fetchMissing.mutate()}>Fetch missing prices</Button>
          <FetcherBadge />
          {fetchMissing.error && <span className="text-danger">{String((fetchMissing.error as Error).message)}</span>}</div>
      </Card>}
      <Card><BulkFetch /></Card>

      <ValueChart />

      <div className="flex flex-wrap items-end gap-2">
        <div className="w-56"><Input aria-label="Search owned" placeholder="Search owned…" value={f.q} onChange={(e) => set({ q: e.target.value })} /></div>
        <div className="w-40"><Select aria-label="Type" value={f.graded} onChange={(v) => set({ graded: v })} allLabel="Raw + graded"
          options={[{ value: "false", label: "Raw" }, { value: "true", label: "Graded" }]} /></div>
        <div className="w-40"><Select aria-label="Condition" value={f.condition} onChange={(v) => set({ condition: v })} allLabel="Any condition"
          options={["NM", "LP", "MP", "HP", "DMG"].map((c) => ({ value: c, label: c }))} /></div>
        <div className="w-40"><Select aria-label="Language" value={f.language} onChange={(v) => set({ language: v })} allLabel="Any language"
          options={["en", "ja", "es", "it", "fr", "de", "pt", "ko", "zh"].map((c) => ({ value: c, label: c.toUpperCase() }))} /></div>
        <div className="w-44"><Select aria-label="Acquired how" value={f.acquisition} onChange={(v) => set({ acquisition: v })} allLabel="Any acquisition"
          options={[...ACQ_TYPES, { value: "unset", label: "Not set" }]} /></div>
        <Checkbox className="py-1.5" label="Needs price" checked={f.needs_price === "true"} onChange={(e) => set({ needs_price: e.target.checked ? "true" : "" })} />
        <Checkbox className="py-1.5" label="No cost" checked={f.cost_missing === "true"} onChange={(e) => set({ cost_missing: e.target.checked ? "true" : "" })} />
        {dirty && <Button variant="ghost" size="sm" onClick={() => set({ q: "", graded: "", language: "", condition: "", needs_price: "", acquisition: "", cost_missing: "" })}>Clear filters</Button>}
      </div>

      <QueryError q={list} label="Collection" />
      {list.isLoading && <Skeleton className="h-64 w-full" />}
      {list.data && items.length === 0 && <EmptyState title="Nothing here">{dirty ? "No stacks match these filters." : "Add cards from the Search page."}</EmptyState>}
      {picked.size > 0 && <div className="flex flex-wrap items-center gap-3 rounded-lg bg-surface-2 px-3 py-2 text-sm" role="status">
        <span>{picked.size} stack{picked.size === 1 ? "" : "s"} selected</span>
        <Button size="sm" onClick={() => { bulk.reset(); setBulkOpen(true); }}>Edit cost &amp; type</Button>
        <Button variant="ghost" size="sm" onClick={() => setPicked(new Set())}>Clear selection</Button>
      </div>}
      {items.length > 0 && <>
        <Table>
          <THead>
            <Th className="w-8"><Checkbox aria-label="Select all on this page" label="" checked={allOnPage} onChange={togglePage} /></Th>
            <Th className="w-12"><span className="sr-only">Image</span></Th>
            {COLS.map((c) => c.key
              ? <SortTh key={c.key} label={c.label} num={c.num} active={f.sort === c.key} dir={dir} onSort={() => sort(c.key)} />
              : <Th key={c.label}>{c.label}</Th>)}
            <Th><span className="sr-only">Actions</span></Th>
          </THead>
          <tbody>
            {items.map((i) => (
              <Tr key={i.id} className="cursor-pointer hover:bg-surface-2" onClick={() => setSel(i)}>
                <Td><span onClick={(e) => e.stopPropagation()}><Checkbox aria-label={`Select ${i.card?.name} ${detail(i)}`} label="" checked={picked.has(i.id)} onChange={() => toggle(i.id)} /></span></Td>
                <Td>{i.card?.images?.small && <img src={i.card.images.small} alt="" loading="lazy" className="h-12 rounded-sm" />}</Td>
                <Td><Link className="font-medium hover:underline" to={`/cards/${encodeURIComponent(i.card_id)}`} onClick={(e) => e.stopPropagation()}>{i.card?.name}</Link></Td>
                <Td className="text-muted">{i.card?.set?.name} #{i.card?.number}</Td>
                <Td className="text-muted">{detail(i)}</Td>
                <Td num>{i.quantity}</Td>
                <Td num><Value i={i} /></Td>
                <Td num><div>{money(i.cost)}</div><AcqBadge type={i.acquired?.type} /></Td>
                <Td num className={i.pl == null ? "text-muted" : i.pl >= 0 ? "text-ok" : "text-danger"}>{i.pl == null ? "—" : money(i.pl)}</Td>
                <Td className="w-16">
                  <span className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                    <Link to={`/alerts?stack=${i.id}`} aria-label={`Create alert for ${i.card?.name}`} title="Create alert" className="rounded p-1 text-muted hover:bg-surface hover:text-fg"><Bell size={14} /></Link>
                    <button type="button" aria-label={`Details for ${i.card?.name}`} title="Details" onClick={() => setSel(i)} className="rounded p-1 text-muted hover:bg-surface hover:text-fg"><ChevronRight size={14} /></button>
                  </span></Td>
              </Tr>))}
          </tbody>
        </Table>
        <Pagination page={Number(f.page)} pageSize={Number(f.size)} total={list.data.total}
          onPage={(p) => set({ page: String(p) }, true)} onPageSize={(n) => set({ size: String(n) })} />
      </>}
      <Drawer open={!!sel} onClose={() => setSel(null)} title={cur?.card?.name ?? "Details"}>{cur && <Details i={cur} />}</Drawer>
      <Drawer open={bulkOpen} onClose={() => { setBulkOpen(false); if (bulk.isSuccess) setPicked(new Set()); }} title={`Edit cost & type · ${picked.size} stack${picked.size === 1 ? "" : "s"}`}>
        <AcquiredForm bulk busy={bulk.isPending} submitLabel={`Apply to ${picked.size}`} onSubmit={(p) => bulk.mutate(p)} />
        {bulk.error && <p role="alert" className="mt-2 text-sm text-danger">{String((bulk.error as Error).message)}</p>}
        {bulk.isSuccess && <p className="mt-2 text-sm text-ok" role="status">Updated {bulk.data.updated}, unchanged {bulk.data.unchanged}{bulk.data.missing.length ? `, ${bulk.data.missing.length} not found` : ""}. Each change is in the stack's edit history.</p>}
      </Drawer>
    </div>
  );
}
