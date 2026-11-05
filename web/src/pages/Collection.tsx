import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, ChevronRight, TriangleAlert } from "lucide-react";
import { api, money } from "../lib/api";
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
const DEFAULTS = { q: "", graded: "", language: "", condition: "", needs_price: "", sort: "added", order: "", page: "1", size: "50" };
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
      <SourceCompare row={i} />
    </div>);
}

export default function Collection() {
  const qc = useQueryClient();
  const [sp, setSp] = useSearchParams();
  const f: Params = { ...DEFAULTS, ...Object.fromEntries(sp) };
  const [sel, setSel] = useState<any>(null);
  const set = (patch: Partial<Params>, keepPage = false) => {
    const next = { ...f, ...(keepPage ? {} : { page: "1" }), ...patch };
    setSp(Object.fromEntries(Object.entries(next).filter(([k, v]) => v !== DEFAULTS[k as keyof Params])), { replace: true });
  };
  const sum = useQuery({ queryKey: ["collection", "summary"], queryFn: api.collectionSummary });
  const query = { q: f.q, graded: f.graded, language: f.language, condition: f.condition, needs_price: f.needs_price,
    sort: f.sort, order: f.order, page: f.page, page_size: f.size };
  const list = useQuery({ queryKey: ["collection", query], queryFn: () => api.collection(query), placeholderData: (p) => p });
  const s = sum.data;
  const { running } = usePriceFetchJob(() => qc.invalidateQueries({ queryKey: ["collection"] }));
  const fetchMissing = useMutation({ mutationFn: () => api.fetchPrices({ missing: true }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["jobs"] }) });
  const dirty = (["q", "graded", "language", "condition", "needs_price"] as const).some((k) => f[k] !== "");
  const dir: "asc" | "desc" = f.order ? (f.order as "asc" | "desc") : DEFAULT_DESC.includes(f.sort) ? "desc" : "asc";
  const sort = (key: string) => key && set(f.sort === key ? { order: dir === "desc" ? "asc" : "desc" } : { sort: key, order: "" });
  const items: any[] = list.data?.items ?? [];

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Collection</h1>
      <QueryError q={sum} label="Summary" />
      {sum.isLoading && <div className="grid grid-cols-2 gap-3 md:grid-cols-5">{[0, 1, 2, 3, 4].map((n) => <Skeleton key={n} className="h-20" />)}</div>}
      {s && <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Kpi label="Cards" value={s.cards} hint={`${s.distinct} distinct`} />
        <Kpi label="Value" value={money(s.value)} />
        <Kpi label="Cost" value={money(s.cost)} />
        <Kpi label="P/L" value={s.pl == null ? "—" : money(s.pl)} tone={s.pl == null ? undefined : s.pl >= 0 ? "ok" : "danger"}
          hint={s.pl != null && s.cost ? `${s.pl >= 0 ? "+" : ""}${((s.pl / s.cost) * 100).toFixed(1)}% of cost` : undefined} />
        <Kpi label="Needs price / estimated" value={`${s.needs_price} / ${s.estimated}`} />
      </div>}
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
        <Checkbox className="py-1.5" label="Needs price" checked={f.needs_price === "true"} onChange={(e) => set({ needs_price: e.target.checked ? "true" : "" })} />
        {dirty && <Button variant="ghost" size="sm" onClick={() => set({ q: "", graded: "", language: "", condition: "", needs_price: "" })}>Clear filters</Button>}
      </div>

      <QueryError q={list} label="Collection" />
      {list.isLoading && <Skeleton className="h-64 w-full" />}
      {list.data && items.length === 0 && <EmptyState title="Nothing here">{dirty ? "No stacks match these filters." : "Add cards from the Search page."}</EmptyState>}
      {items.length > 0 && <>
        <Table>
          <THead>
            <Th className="w-12"><span className="sr-only">Image</span></Th>
            {COLS.map((c) => c.key
              ? <SortTh key={c.key} label={c.label} num={c.num} active={f.sort === c.key} dir={dir} onSort={() => sort(c.key)} />
              : <Th key={c.label}>{c.label}</Th>)}
            <Th><span className="sr-only">Actions</span></Th>
          </THead>
          <tbody>
            {items.map((i) => (
              <Tr key={i.id} className="cursor-pointer hover:bg-surface-2" onClick={() => setSel(i)}>
                <Td>{i.card?.images?.small && <img src={i.card.images.small} alt="" loading="lazy" className="h-12 rounded-sm" />}</Td>
                <Td><Link className="font-medium hover:underline" to={`/cards/${encodeURIComponent(i.card_id)}`} onClick={(e) => e.stopPropagation()}>{i.card?.name}</Link></Td>
                <Td className="text-muted">{i.card?.set?.name} #{i.card?.number}</Td>
                <Td className="text-muted">{detail(i)}</Td>
                <Td num>{i.quantity}</Td>
                <Td num><Value i={i} /></Td>
                <Td num>{money(i.cost)}</Td>
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
      <Drawer open={!!sel} onClose={() => setSel(null)} title={sel?.card?.name ?? "Details"}>{sel && <Details i={sel} />}</Drawer>
    </div>
  );
}
