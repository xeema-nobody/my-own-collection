import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp } from "lucide-react";
import { api, money } from "../lib/api";
import { QueryError } from "../components/QueryState";
import FetchProgress from "../components/FetchProgress";
import FetcherBadge from "../components/FetcherBadge";
import ValueChart from "../components/ValueChart";
import { usePriceFetchJob } from "../lib/fetchJob";
import { SOURCE_COLOR } from "../lib/colors";
import { Badge, BarList, Button, EmptyState, Kpi, Section, SegmentedControl, Skeleton, Table, THead, Td, Th, Tr } from "../components/ui";

const KIND_TONE = { sold: "ok", market: "neutral", ask: "warn" } as const;
const BREAKDOWNS = ["set", "rarity", "condition", "language", "tcg"] as const;
type By = (typeof BREAKDOWNS)[number];
const grade = (m: any) => (m.grade_key === "raw" ? "raw" : m.grade_key);

/** Percent change between the first and last snapshot that carry a v2 `total_value`; null with fewer than two. */
export function changePct(hist: any[] | undefined): number | null {
  const cmp = (hist ?? []).filter((s) => s.total_value != null);
  if (cmp.length < 2) return null;
  const old = cmp[0].total_value;
  return old ? ((cmp.at(-1).total_value - old) / old) * 100 : null;
}

function Mover({ m }: { m: any }) {
  const up = m.pct >= 0;
  return (
    <li className="flex items-center justify-between gap-3 text-sm" title={`via ${m.source}${m.match === "exact" ? "" : ` (${m.match})`}`}>
      <span className="min-w-0">
        <Link className="font-medium hover:underline" to={`/cards/${encodeURIComponent(m.card_id)}`}>{m.name}</Link>{" "}
        <span className="text-muted">{grade(m)}</span>{" "}
        <Badge tone={KIND_TONE[m.kind as keyof typeof KIND_TONE] ?? "neutral"}>{m.kind}</Badge>
      </span>
      <span className="num shrink-0 text-right">
        <span className="text-muted">{money(m.from)} → {money(m.to)}</span>{" "}
        <span className={up ? "text-ok" : "text-danger"}>{up ? "▲" : "▼"} {Math.abs(m.pct)}%</span>
      </span>
    </li>);
}

export default function Dashboard() {
  const [by, setBy] = useState<By>("set");
  const qc = useQueryClient();
  const sum = useQuery({ queryKey: ["collection", "summary"], queryFn: api.collectionSummary });
  const hist30 = useQuery({ queryKey: ["history", "change30"], queryFn: () => api.history(30) });
  const brk = useQuery({ queryKey: ["breakdown", by], queryFn: () => api.breakdown(by) });
  const mov = useQuery({ queryKey: ["movers"], queryFn: () => api.movers(7) });
  const top = useQuery({ queryKey: ["collection", "top"], queryFn: () => api.collection({ sort: "value", order: "desc", page_size: 8 }) });
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: api.jobs, refetchInterval: 5000 });
  const { running, latest } = usePriceFetchJob(() => qc.invalidateQueries());
  const refresh = useMutation({ mutationFn: () => api.refreshPrices("collection"), onSuccess: () => qc.invalidateQueries() });
  const snap = useMutation({ mutationFn: api.snapshot, onSuccess: () => qc.invalidateQueries({ queryKey: ["history"] }) });
  const fetchMissing = useMutation({ mutationFn: () => api.fetchPrices({ missing: true }), onSettled: () => qc.invalidateQueries({ queryKey: ["jobs"] }) });

  const s = sum.data;
  const delta = changePct(hist30.data);
  const soldPct = s?.value ? Math.round(((s.value_by_kind?.sold ?? 0) / s.value) * 100) : null;
  const plPct = s?.pl != null && s.cost ? (s.pl / s.cost) * 100 : null;
  const lastRun = jobs.data?.find((j: any) => j.type === "price_refresh");
  const movers: any[] = [...(mov.data?.up ?? []), ...(mov.data?.down ?? [])];
  const holdings: any[] = (top.data?.items ?? []).filter((i: any) => i.value != null);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted">How the collection is doing and what changed. Inventory and editing live in Collection.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs text-muted">Last refresh: {lastRun ? `${lastRun.finished_at?.slice(0, 16).replace("T", " ") ?? "running"} (${lastRun.status})` : "never"}</span>
          <Button variant="secondary" disabled={refresh.isPending} onClick={() => refresh.mutate()}>Refresh prices</Button>
          <Button variant="ghost" disabled={snap.isPending} onClick={() => snap.mutate()}>Snapshot now</Button>
        </div>
      </div>
      <QueryError q={sum} label="Summary" /><QueryError q={hist30} label="History" /><QueryError q={brk} label="Breakdown" /><QueryError q={mov} label="Movers" /><QueryError q={top} label="Top holdings" /><QueryError q={jobs} label="Jobs" />

      {sum.isLoading ? <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[0, 1, 2, 3].map((n) => <Skeleton key={n} className="h-20" />)}</div> : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Kpi label="Value" value={money(s?.value)} hint={s?.estimated > 0 ? `${s.estimated} estimated` : undefined} />
          <Kpi label="Change (30d)" value={delta == null ? "—" : `${delta >= 0 ? "▲" : "▼"} ${Math.abs(delta).toFixed(1)}%`}
            tone={delta == null ? undefined : delta >= 0 ? "ok" : "danger"} hint={delta == null ? "needs 2 snapshots" : undefined} />
          <Kpi label="P/L" value={s?.pl == null ? "—" : money(s.pl)} tone={s?.pl == null ? undefined : s.pl >= 0 ? "ok" : "danger"}
            hint={plPct == null ? undefined : `${plPct >= 0 ? "+" : ""}${plPct.toFixed(1)}% vs cost`} />
          <Kpi label="Cost" value={money(s?.cost)} />
        </div>)}

      <ValueChart full height="h-72" />

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Where the value is" actions={
          <SegmentedControl label="Group by" value={by} onChange={setBy} options={BREAKDOWNS.map((b) => ({ value: b, label: b }))} />}>
          {brk.isLoading && <Skeleton className="h-40 w-full" />}
          {brk.data && brk.data.length === 0 && <EmptyState title="Nothing valued yet">Add cards from Search and fetch prices.</EmptyState>}
          {brk.data && brk.data.length > 0 && <BarList label={`Value by ${by}`} rows={brk.data} format={money} />}
        </Section>

        <Section title="Top holdings" actions={<Link className="text-xs text-accent hover:underline" to="/collection?sort=value">All stacks</Link>}>
          {top.isLoading && <Skeleton className="h-40 w-full" />}
          {top.data && holdings.length === 0 && <EmptyState title="No valued stacks">Stacks without a price are not ranked.</EmptyState>}
          {holdings.length > 0 && (
            <ol className="space-y-2">
              {holdings.map((i: any) => (
                <li key={i.id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="min-w-0">
                    <Link className="font-medium hover:underline" to={`/cards/${encodeURIComponent(i.card_id)}`}>{i.card?.name}</Link>{" "}
                    <span className="text-muted">{i.grading ? `${i.grading.company} ${i.grading.grade}` : i.condition}{i.quantity > 1 ? ` ×${i.quantity}` : ""}</span>
                  </span>
                  <span className="num shrink-0"><span className="font-semibold">{money(i.value)}</span>{" "}
                    <Badge tone={KIND_TONE[i.price_kind as keyof typeof KIND_TONE] ?? "neutral"}>{i.price_kind}</Badge></span>
                </li>))}
            </ol>)}
        </Section>

        <Section title="Top movers (7d)">
          {mov.isLoading && <Skeleton className="h-40 w-full" />}
          {mov.data && movers.length === 0 && (
            <EmptyState title="No moves yet">{s?.distinct === 0 ? "No cards owned yet: add some from Search."
              : "An item needs the same kind of price (sold / market, same grade match) today and 7 days ago. This fills in as snapshots accumulate."}</EmptyState>)}
          {movers.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2">
              {([["Up", mov.data.up, ArrowUp], ["Down", mov.data.down, ArrowDown]] as const).map(([label, list, Icon]) => (
                <div key={label}>
                  <h3 className="mb-2 flex items-center gap-1 text-xs font-medium text-muted"><Icon size={12} aria-hidden />{label}</h3>
                  {list.length ? <ul className="space-y-2">{list.map((m: any) => <Mover key={`${m.card_id}-${m.grade_key}`} m={m} />)}</ul> : <p className="text-sm text-muted">None</p>}
                </div>))}
            </div>)}
        </Section>

        <Section title="Data quality">
          {sum.isLoading && <Skeleton className="h-40 w-full" />}
          {s && (
            <div className="space-y-3 text-sm">
              <div>
                <div className="flex justify-between"><span>Sold-based value</span><span className="num font-medium">{soldPct == null ? "—" : `${soldPct}%`}</span></div>
                <div className="mt-1 h-1.5 rounded-full bg-surface-2"><div role="presentation" className="h-full rounded-full bg-ok" style={{ width: `${soldPct ?? 0}%` }} /></div>
                <p className="mt-1 text-xs text-muted">Share of value backed by recent sales (≥ 3 in 90 days); the rest uses market prices.</p>
              </div>
              <ul className="space-y-1">
                <li className="flex justify-between"><span className="text-muted">Estimated (bucket / lower grade)</span><span className="num">{s.estimated ?? 0}</span></li>
                <li className="flex justify-between"><span className="text-muted">Need a graded price (not counted)</span><span className="num">{s.needs_price ?? 0}</span></li>
                <li className="flex justify-between"><span className="text-muted">No data</span><span className="num">{s.no_data ?? 0}</span></li>
              </ul>
              {s.needs_price > 0 && (
                <div className="flex flex-wrap items-center gap-3">
                  <Button size="sm" disabled={!!running || fetchMissing.isPending} onClick={() => fetchMissing.mutate()}>Fetch missing prices</Button>
                  <FetcherBadge />
                  {fetchMissing.error && <span className="text-danger">{String((fetchMissing.error as Error).message)}</span>}
                </div>)}
              <FetchProgress job={running ?? (fetchMissing.isSuccess ? latest : undefined)} live={!!running} />
            </div>)}
        </Section>
      </div>

      <Section title="Source comparison" collapsible id="dashboard-sources" defaultOpen={false}>
        <Table>
          <THead><Th>Source</Th><Th num>Total</Th><Th num>Items priced</Th><Th num>vs headline (same items)</Th></THead>
          <tbody>
            {Object.entries(s?.by_source ?? {}).map(([k, v]: any) => (
              <Tr key={k}>
                <Td><span className="mr-2 inline-block h-2 w-2 rounded-full align-middle" style={{ background: SOURCE_COLOR[k] }} aria-hidden />{k}</Td>
                <Td num>{money(v.value)}</Td><Td num>{v.items}/{s.distinct}</Td>
                <Td num>{v.vs_headline_pct == null ? "—" : <Badge tone={v.far ? "warn" : "neutral"} title={v.far ? "Far from the headline valuation" : ""}>{v.vs_headline_pct > 0 ? "+" : ""}{v.vs_headline_pct}%</Badge>}</Td>
              </Tr>))}
          </tbody>
        </Table>
        <p className="mt-2 text-xs text-muted">Headline = best price per item (sold first, then preferred source). Totals per source use only that source and may cover fewer items.</p>
      </Section>
    </div>);
}
