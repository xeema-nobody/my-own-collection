import { useMemo, useState } from "react";
import { useMutation, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { api } from "../../lib/api";
import { errorText } from "../../components/QueryState";
import { Badge, Button, Checkbox, Chip, Drawer, EmptyState, Input, Section, Table, THead, Td, Th, Tr } from "../../components/ui";

type Filter = "not_imported" | "incomplete" | "no_prices";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "not_imported", label: "Not imported" }, { key: "incomplete", label: "Incomplete" }, { key: "no_prices", label: "No prices" },
];
const match = (f: Filter, x: any) =>
  f === "not_imported" ? x.cards_total === 0 : f === "incomplete" ? x.cards_missing > 0 : x.cards_total > 0 && x.cards_priced === 0;

function SetState({ x }: { x: any }) {
  if (x.cards_total === 0) return <Badge tone="warn">not imported</Badge>;
  if (x.cards_missing > 0) return <Badge tone="danger" title={`Imported ${x.cards_total} of ${x.cards_expected} cards`}>{x.cards_missing} missing</Badge>;
  if (x.cards_priced === 0) return <Badge title="No price block in the source payload">no price source</Badge>;
  return <Badge tone="ok">complete</Badge>;
}

export default function CatalogTab({ sets, jobs, picked, setPicked }: {
  sets: UseQueryResult<any[]>; jobs: UseQueryResult<any[]>; picked: Set<string>; setPicked: (s: Set<string>) => void;
}) {
  const qc = useQueryClient();
  const [filter, setFilter] = useState("");
  const [flags, setFlags] = useState<Filter[]>([]);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState<null | "import_all">(null);
  const done = () => { qc.invalidateQueries({ queryKey: ["jobs"] }); qc.invalidateQueries({ queryKey: ["sets"] }); };
  const imp = useMutation({ mutationFn: (ids?: string[]) => api.importCatalog(ids), onSettled: done });
  const retry = useMutation({ mutationFn: api.retryIncompleteImports, onSettled: done });
  const ref = useMutation({ mutationFn: (a: { scope: string; sets?: string[] }) => api.refreshPrices(a.scope, a.sets), onSettled: done });

  const audit = useMutation({ mutationFn: api.catalogAudit });
  const a = audit.data;

  const running = (type: string) => jobs.data?.find((j: any) => j.type === type && j.status === "running");
  const importing = !!running("catalog_import"), refreshing = !!running("price_refresh");
  const lastFull = jobs.data?.find((j: any) => j.type === "catalog_import" && j.status !== "running" &&
    (["full", "retry"].includes(j.stats?.origin) || (!j.stats?.origin && !j.stats?.set)));
  const failed: string[] = lastFull?.stats?.failed_sets ?? [];
  const all: any[] = sets.data ?? [];
  const incomplete = [...new Set([...all.filter((x) => x.cards_missing > 0).map((x) => x.external_id), ...failed])];

  const shown = useMemo(() => all.filter((x) =>
    `${x.name} ${x.external_id}`.toLowerCase().includes(filter.toLowerCase()) && flags.every((f) => match(f, x))), [all, filter, flags]);
  const groups = useMemo(() => {
    const m = new Map<string, any[]>();
    shown.forEach((x) => { const k = x.series || "Other"; m.set(k, [...(m.get(k) ?? []), x]); });
    return [...m.entries()]; // sets arrive newest first, so groups do too
  }, [shown]);
  const searching = filter !== "" || flags.length > 0;
  const isOpen = (k: string) => searching || open.has(k);
  const toggleGroup = (k: string) => setOpen((o) => { const n = new Set(o); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const toggleSet = (id: string) => { const n = new Set(picked); n.has(id) ? n.delete(id) : n.add(id); setPicked(n); };
  const toggleMany = (ids: string[], on: boolean) => { const n = new Set(picked); ids.forEach((i) => (on ? n.add(i) : n.delete(i))); setPicked(n); };
  const ids = [...picked];
  const err = imp.error || retry.error || ref.error;
  const run = (j: any) => j && `${j.type.replace("_", " ")} ${j.stats?.cards ?? 0} cards`;

  return (
    <div className="space-y-4">
      <Section title="Actions" id="settings-actions">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Selected sets ({ids.length})</h3>
            <div className="flex flex-wrap gap-2">
              <Button disabled={importing || !ids.length} onClick={() => imp.mutate(ids)}>Import selected</Button>
              <Button variant="secondary" disabled={refreshing || !ids.length} onClick={() => ref.mutate({ scope: "tracked", sets: ids })}>Refresh tracked prices</Button>
            </div>
          </div>
          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Everything</h3>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" disabled={importing || !incomplete.length} onClick={() => retry.mutate()}>Retry incomplete ({incomplete.length})</Button>
              <Button variant="secondary" disabled={importing} onClick={() => setConfirm("import_all")}>Import all</Button>
              <Button variant="secondary" disabled={refreshing} onClick={() => ref.mutate({ scope: "tracked" })}>Refresh tracked prices</Button>
            </div>
          </div>
        </div>
        {err && <p className="mt-3 text-sm text-danger">{errorText(err)}</p>}
        {(importing || refreshing) && <p className="mt-3 text-sm text-warn">Running: {[running("catalog_import"), running("price_refresh")].filter(Boolean).map(run).join(" · ")}</p>}
        <p className="mt-3 text-xs text-muted">Prices are stored only for tracked cards (collection + wishlist); the catalog import stores cards, not prices. Jobs run in the background, one per type at a time. Progress on the Jobs tab.</p>
      </Section>

      <Section title="Coverage audit" id="settings-audit">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" disabled={audit.isPending} onClick={() => audit.mutate()}>{audit.isPending ? "Checking…" : "Check coverage"}</Button>
          {a && <Button size="sm" variant="ghost" disabled={!a.to_import.length} onClick={() => setPicked(new Set(a.to_import))}>Select gaps ({a.to_import.length})</Button>}
          <span className="text-xs text-muted">Compares the source's live set list with what is stored. One request, no card download.</span>
        </div>
        {audit.error && <p className="mt-3 text-sm text-danger">{errorText(audit.error)}</p>}
        {a && (<>
          <p className="mt-3 text-sm text-muted">{a.sets} sets, {a.cards} cards · {a.promo_sets} promo / other sets · {a.secret_over_printed} sets hold secret rares above the printed total (normal) · {a.provider_only.length} new at the source · {a.code_missing.length} without printed code</p>
          {a.rows.length === 0 ? <p className="mt-2 text-sm text-ok">No gaps.</p> : (
            <Table className="mt-3 max-h-80 overflow-y-auto">
              <THead><Th>Set</Th><Th num>Stored</Th><Th num>Source total</Th><Th>Issue</Th></THead>
              <tbody>{a.rows.map((r: any) => (
                <Tr key={r.id}><Td>{r.name} <span className="text-xs text-muted">{r.id}{r.promo ? " · promo" : ""}</span></Td>
                  <Td num>{r.imported}</Td><Td num>{r.provider_total ?? "—"}</Td>
                  <Td>{r.issues.filter((i: string) => i !== "over_total").map((i: string) => <Badge key={i} tone={i === "short" || i === "new_at_provider" || i === "empty" ? "warn" : undefined}>{i.replace(/_/g, " ")}</Badge>)}</Td></Tr>))}</tbody>
            </Table>)}
        </>)}
      </Section>

      <Section title={`Sets (${shown.length}${shown.length !== all.length ? ` of ${all.length}` : ""})`} id="settings-sets">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="w-64"><Input aria-label="Filter sets" placeholder="Filter by name or id…" value={filter} onChange={(e) => setFilter(e.target.value)} /></div>
          {FILTERS.map((f) => <Chip key={f.key} active={flags.includes(f.key)} onClick={() => setFlags((v) => v.includes(f.key) ? v.filter((y) => y !== f.key) : [...v, f.key])}>{f.label}</Chip>)}
          <span className="ml-auto flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => toggleMany(shown.map((x) => x.external_id), true)}>Select shown</Button>
            <Button size="sm" variant="ghost" disabled={!incomplete.length} onClick={() => setPicked(new Set(incomplete))}>Select incomplete</Button>
            <Button size="sm" variant="ghost" disabled={!ids.length} onClick={() => setPicked(new Set())}>Clear ({ids.length})</Button>
          </span>
        </div>
        {sets.isLoading ? null : groups.length === 0 ? <EmptyState title="No sets match">Clear the filters, or import the catalog first.</EmptyState> : (
          <Table className="max-h-[32rem] overflow-y-auto">
            <THead><Th className="w-8" /><Th>Set</Th><Th>Released</Th><Th num>Cards</Th><Th num>Priced</Th><Th>State</Th></THead>
            <tbody>
              {groups.map(([series, rows]) => {
                const sel = rows.filter((x) => picked.has(x.external_id)).length;
                const rowIds = rows.map((x) => x.external_id);
                return [
                  <Tr key={series} className="bg-surface-2/50">
                    <Td><input type="checkbox" aria-label={`Select all in ${series}`} className="h-4 w-4 accent-[rgb(var(--accent))]"
                      checked={sel === rows.length} ref={(el) => { if (el) el.indeterminate = sel > 0 && sel < rows.length; }}
                      onChange={(e) => toggleMany(rowIds, e.target.checked)} /></Td>
                    <Td colSpan={5}>
                      <button type="button" aria-expanded={isOpen(series)} onClick={() => toggleGroup(series)} className="flex items-center gap-1 font-medium">
                        <ChevronRight size={14} className={isOpen(series) ? "rotate-90 transition" : "transition"} aria-hidden />
                        {series}<span className="ml-1 text-xs font-normal text-muted">{rows.length} sets{sel > 0 && ` · ${sel} selected`}</span>
                      </button>
                    </Td>
                  </Tr>,
                  ...(isOpen(series) ? rows.map((x) => (
                    <Tr key={x.external_id}>
                      <Td><input type="checkbox" aria-label={`Select ${x.name}`} className="h-4 w-4 accent-[rgb(var(--accent))]" checked={picked.has(x.external_id)} onChange={() => toggleSet(x.external_id)} /></Td>
                      <Td>{x.name} <span className="text-xs text-muted">{x.external_id}</span></Td>
                      <Td className="whitespace-nowrap text-muted">{x.release_date?.slice(0, 10) ?? "—"}</Td>
                      <Td num className={x.cards_missing > 0 ? "text-danger" : ""}>{x.cards_total}{x.cards_expected ? ` / ${x.cards_expected}` : ""}</Td>
                      <Td num>{x.cards_priced}</Td>
                      <Td><SetState x={x} /></Td>
                    </Tr>)) : []),
                ];
              })}
            </tbody>
          </Table>)}
      </Section>

      <Drawer open={confirm !== null} onClose={() => setConfirm(null)} title="Import all sets?">
        <p className="text-sm text-muted">Imports every set from the catalog source (cards only, no prices). This can take 30 minutes or more and runs in the background.</p>
        <div className="mt-4 flex gap-2">
          <Button onClick={() => { imp.mutate(undefined); setConfirm(null); }}>Start</Button>
          <Button variant="ghost" onClick={() => setConfirm(null)}>Cancel</Button>
        </div>
      </Drawer>
    </div>);
}
