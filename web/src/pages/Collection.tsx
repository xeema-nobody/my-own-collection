import { useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, ChevronRight, TriangleAlert } from "lucide-react";
import { api, money, ago } from "../lib/api";
import AcquiredForm, { ACQ_TYPES, AcqBadge, acqLabel } from "../components/AcquiredForm";
import { QueryError } from "../components/QueryState";
import SourceCompare from "../components/SourceCompare";
import BulkFetch, { fetchErrorText } from "../components/BulkFetch";
import FetcherBadge from "../components/FetcherBadge";
import Filters from "../components/collection/Filters";
import Grid from "../components/collection/Grid";
import PresetBar from "../components/collection/PresetBar";
import { Value, detail, whyEstimated } from "../components/collection/parts";
import { useUrlState } from "../lib/urlState";
import { useStoredState } from "../lib/storedState";
import { BUILTIN_PRESETS, COLLECTION_DEFAULTS, DEFAULT_DESC, PRESET_KEYS, activeFilterCount, toApiQuery } from "../lib/collectionList";
import ValueChart from "../components/ValueChart";
import { usePriceFetchJob } from "../lib/fetchJob";
import { Badge, Button, Card, Checkbox, Drawer, EmptyState, Kpi, Pagination, Skeleton, SortTh, Table, THead, Td, Th, Tr, ViewToggle, VIEWS } from "../components/ui";

const COLS: { key: string; label: string; num?: boolean }[] = [
  { key: "name", label: "Card" }, { key: "set", label: "Set" }, { key: "", label: "Details" },
  { key: "qty", label: "Qty", num: true }, { key: "value", label: "Value", num: true },
  { key: "cost", label: "Cost", num: true }, { key: "pl", label: "P/L", num: true },
];
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
  const [view, setView] = useStoredState("collection.view", "table", VIEWS);
  const [f, set] = useUrlState(COLLECTION_DEFAULTS);
  const [sel, setSel] = useState<any>(null);
  // lists change little between visits: serve the cached page instantly and refresh quietly in the background
  const cached = { staleTime: 60_000, gcTime: 30 * 60_000 };
  const sum = useQuery({ queryKey: ["collection", "summary"], queryFn: api.collectionSummary, ...cached });
  const facets = useQuery({ queryKey: ["collection", "facets"], queryFn: api.collectionFacets, ...cached });
  const query = toApiQuery(f);
  const list = useQuery({ queryKey: ["collection", "list", query], queryFn: () => api.collection(query), placeholderData: keepPreviousData, ...cached });
  const s = sum.data;
  const { running } = usePriceFetchJob(() => qc.invalidateQueries({ queryKey: ["collection"] }));
  const fetchMissing = useMutation({ mutationFn: () => api.fetchPrices({ missing: true }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["jobs"] }) });
  const bulk = useMutation({ mutationFn: (acquired: any) => api.bulkAcquired([...picked], acquired),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["collection"] }); qc.invalidateQueries({ queryKey: ["stack-history"] }); } });
  const dirty = activeFilterCount(f) > 0;
  const dir: "asc" | "desc" = f.order ? (f.order as "asc" | "desc") : DEFAULT_DESC.includes(f.sort) ? "desc" : "asc";
  const sort = (key: string) => key && set(f.sort === key ? { order: dir === "desc" ? "asc" : "desc" } : { sort: key, order: "" });
  const t = list.data?.totals;
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

      <PresetBar scope="collection" state={f} defaults={COLLECTION_DEFAULTS} keys={PRESET_KEYS} builtins={BUILTIN_PRESETS} onApply={set} />
      <Filters f={f} set={set} facets={facets.data} dir={dir} onDir={(d) => set({ order: d })} />
      {dirty && t && <div className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-lg bg-surface-2 px-3 py-2 text-sm" role="status" aria-label="Filtered totals">
        <span className="font-medium">{t.stacks} stack{t.stacks === 1 ? "" : "s"} match</span>
        <span className="num text-muted">{t.cards} cards</span>
        <span className="num">Value <span className="font-semibold">{money(t.value)}</span></span>
        <span className="num">Cost <span className="font-semibold">{money(t.cost)}</span>{t.cost_missing > 0 && <span className="text-muted"> ({t.cost_missing} without)</span>}</span>
        <span className={`num ${t.pl == null ? "text-muted" : t.pl >= 0 ? "text-ok" : "text-danger"}`}>P/L <span className="font-semibold">{t.pl == null ? "—" : money(t.pl)}</span></span>
      </div>}
      <div className="flex justify-end"><ViewToggle value={view} onChange={setView} /></div>

      <QueryError q={list} label="Collection" />
      {list.isLoading && <Skeleton className="h-64 w-full" />}
      {list.data && items.length === 0 && <EmptyState title="Nothing here">{dirty ? "No stacks match these filters." : "Add cards from the Search page."}</EmptyState>}
      {picked.size > 0 && <div className="flex flex-wrap items-center gap-3 rounded-lg bg-surface-2 px-3 py-2 text-sm" role="status">
        <span>{picked.size} stack{picked.size === 1 ? "" : "s"} selected</span>
        <Button size="sm" onClick={() => { bulk.reset(); setBulkOpen(true); }}>Edit cost &amp; type</Button>
        <Button variant="ghost" size="sm" onClick={() => setPicked(new Set())}>Clear selection</Button>
      </div>}
      {items.length > 0 && <>
        {view === "grid" ? <Grid items={items} picked={picked} onToggle={toggle} onOpen={setSel} /> : <Table>
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
        </Table>}
        <Pagination page={Number(f.page)} pageSize={Number(f.size)} total={list.data?.total ?? 0}
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
