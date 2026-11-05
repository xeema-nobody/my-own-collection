import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { api, money, type WishEntry } from "../lib/api";
import { eurosToCents, filterWishes, searchWishes, sortWishes, wantLabel, wishDir, WISH_SORTS, type WishFilter } from "../lib/wishlist";
import { useUrlState } from "../lib/urlState";
import { useStoredState } from "../lib/storedState";
import PresetBar from "../components/collection/PresetBar";
import BulkFetch from "../components/BulkFetch";
import { QueryError } from "../components/QueryState";
import { Badge, Button, Card, Checkbox, Chip, Drawer, EmptyState, Field, Input, Kpi, SegmentedControl, Select, Skeleton, SortTh, Table, THead, Td, Th, Tr, ViewToggle, VIEWS } from "../components/ui";

const KIND_TONE = { sold: "ok", market: "neutral", ask: "warn" } as const;

function Price({ w }: { w: WishEntry }) {
  if (w.needs_price) return <Badge tone="warn" title="No graded price yet; fetch prices for this card">needs price</Badge>;
  if (w.value == null) return <span className="text-muted" title="No price for this version">no price</span>;
  return <span className="inline-flex items-center justify-end gap-1.5">
    {w.estimated && <span title="Estimated price" className="text-warn">≈</span>}<span className="font-semibold">{money(w.value)}</span>
    {w.price_kind && <Badge tone={KIND_TONE[w.price_kind as keyof typeof KIND_TONE] ?? "neutral"}>{w.price_kind}</Badge>}</span>;
}

function Gap({ w }: { w: WishEntry }) {
  if (w.target_price == null) return <span className="text-muted">no target</span>;
  if (w.gap == null) return <span className="text-muted">—</span>;
  return w.hit
    ? <Badge tone="ok">target hit · {money(-w.gap)} under</Badge>
    : <span className="text-muted">{money(w.gap)} above</span>;
}

function EditDrawer({ w, onClose }: { w: WishEntry | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [target, setTarget] = useState("");
  const [note, setNote] = useState("");
  const [alert, setAlert] = useState(true);
  const [err, setErr] = useState("");
  const [key, setKey] = useState<string | null>(null);
  if (w && key !== w.id) {   // load the entry into the form when a new one opens
    setKey(w.id); setErr(""); setNote(w.note ?? ""); setAlert(w.alert); setTarget(w.target_price != null ? (w.target_price / 100).toFixed(2) : "");
  }
  const save = useMutation({
    mutationFn: (b: { target_price: number | null; note: string | null; alert: boolean }) => api.patchWish(w!.id, b),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["wishlist"] }); qc.invalidateQueries({ queryKey: ["alerts"] }); onClose(); },
    onError: (e: Error) => setErr(e.message),
  });
  const submit = () => {
    const cents = eurosToCents(target);
    if (cents === undefined) return setErr("Target must be above 0 (or empty)");
    save.mutate({ target_price: cents, note: note.trim() || null, alert });
  };
  return (
    <Drawer open={!!w} onClose={onClose} title={w ? `Edit ${w.card?.name ?? w.card_id} (${wantLabel(w)})` : "Edit"}>
      <div className="space-y-3 text-sm">
        <Field label="Target price (€)"><Input type="number" step="0.01" min="0" value={target} onChange={(e) => setTarget(e.target.value)} /></Field>
        <Field label="Note"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <Checkbox label="Alert me when the price is below target" checked={alert} onChange={(e) => setAlert(e.target.checked)} />
        {err && <p role="alert" className="text-danger">{err}</p>}
        <div className="flex gap-2">
          <Button disabled={save.isPending} onClick={submit}>Save</Button>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </Drawer>);
}

const WISH_DEFAULTS = { q: "", filter: "", sort: "added", order: "" };
const WISH_KEYS = ["q", "filter", "sort", "order"] as const;
const WISH_PRESETS: { name: string; query: Record<string, string> }[] = [
  { name: "Closest to target", query: { sort: "gap", order: "asc" } },
  { name: "Cheapest first", query: { sort: "value", order: "asc" } },
];

export default function Wishlist() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["wishlist"], queryFn: () => api.wishlist() });
  const [f, set] = useUrlState(WISH_DEFAULTS);
  const [view, setView] = useStoredState("wishlist.view", "table", VIEWS);
  const filter: WishFilter = f.filter === "hit" || f.filter === "noprice" ? f.filter : "all";
  const setFilter = (v: WishFilter) => set({ filter: v === "all" ? "" : v });
  const [edit, setEdit] = useState<WishEntry | null>(null);
  const [confirm, setConfirm] = useState<WishEntry | null>(null);
  const del = useMutation({
    mutationFn: (id: string) => api.removeWish(id),
    onSuccess: () => { setConfirm(null); qc.invalidateQueries({ queryKey: ["wishlist"] }); qc.invalidateQueries({ queryKey: ["alerts"] }); },
  });
  const fresh = useQuery({ queryKey: ["wishlist", "prices"], queryFn: api.wishlistPrices });
  const all = q.data ?? [];
  const rows = sortWishes(searchWishes(filterWishes(all, filter), f.q), f.sort, f.order);
  const dir = wishDir(f.sort, f.order);
  const sortBy = (key: string) => set(f.sort === key ? { order: dir === "desc" ? "asc" : "desc" } : { sort: key, order: "" });
  const hits = all.filter((w) => w.hit).length;
  const priced = all.filter((w) => w.value != null && w.target_price != null);
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Kpi label="Wanted" value={all.length} hint="cards on the wishlist" />
        <Kpi label="Target hit" value={hits} tone={hits ? "ok" : undefined} hint="at or below your target price" />
        <Kpi label="Cost to buy all hits" value={money(all.filter((w) => w.hit).reduce((n, w) => n + (w.value ?? 0), 0))}
          hint={`${priced.length} of ${all.length} have a target and a price`} />
      </div>
      {all.length > 0 && (
        <Card>
          <BulkFetch defaultScope="wishlist" />
          {fresh.data && (
            <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
              Price freshness ({fresh.data.cards} cards):
              <Badge tone="ok">{fresh.data.fresh} fresh (≤{fresh.data.fresh_days} d)</Badge>
              <Badge tone={fresh.data.stale ? "warn" : "neutral"}>{fresh.data.stale} stale</Badge>
              <Badge tone={fresh.data.never ? "warn" : "neutral"}>{fresh.data.never} never fetched</Badge></p>)}
        </Card>)}
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter">
        <Chip active={filter === "all"} onClick={() => setFilter("all")}>All</Chip>
        <Chip active={filter === "hit"} onClick={() => setFilter(filter === "hit" ? "all" : "hit")}>Target hit</Chip>
        <Chip active={filter === "noprice"} onClick={() => setFilter(filter === "noprice" ? "all" : "noprice")}>No price</Chip>
        <div className="w-56"><Input aria-label="Search wishlist" placeholder="Search name, set, note…" value={f.q} onChange={(e) => set({ q: e.target.value })} /></div>
        <div className="ml-auto flex items-center gap-2">
          <div className="w-40"><Select aria-label="Sort by" value={f.sort} onChange={(v) => set({ sort: v, order: "" })} options={WISH_SORTS} /></div>
          <SegmentedControl label="Sort direction" value={dir} onChange={(d) => set({ order: d })} options={[{ value: "desc", label: "↓" }, { value: "asc", label: "↑" }]} />
          <ViewToggle value={view} onChange={setView} />
        </div>
      </div>
      <PresetBar scope="wishlist" state={f} defaults={WISH_DEFAULTS} keys={WISH_KEYS} builtins={WISH_PRESETS} onApply={set} />
      <QueryError q={q} label="Wishlist" />
      {q.isLoading && <Skeleton className="h-40" />}
      {q.data && all.length === 0 && <EmptyState title="Nothing on your wishlist">Open a card and use “Add to wishlist”.</EmptyState>}
      {q.data && all.length > 0 && rows.length === 0 && <EmptyState title="No entries match this filter" />}
      {rows.length > 0 && view === "grid" && (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6" aria-label="Wishlist grid">
          {rows.map((w) => (
            <li key={w.id} className="flex flex-col gap-1.5 rounded-lg border border-line bg-surface p-2 text-sm">
              <Link to={`/cards/${encodeURIComponent(w.card_id)}`} className="flex flex-col gap-1.5 hover:text-accent">
                {w.card?.images?.small ? <img src={w.card.images.small} alt="" loading="lazy" className="aspect-[5/7] w-full rounded object-contain" /> : <div className="aspect-[5/7] w-full rounded bg-surface-2" />}
                <span className="truncate font-medium">{w.card?.name ?? w.card_id} {w.card?.number && `#${w.card.number}`}</span></Link>
              <span className="truncate text-xs text-muted">{w.card?.set?.name}</span>
              <div className="flex items-center justify-between gap-1"><Badge tone={w.grading ? "accent" : "neutral"}>{wantLabel(w)}</Badge><Price w={w} /></div>
              <div className="text-xs"><Gap w={w} /></div>
              <div className="flex justify-end">
                <Button variant="ghost" size="sm" aria-label={`Edit ${w.card?.name} ${wantLabel(w)}`} onClick={() => setEdit(w)}><Pencil size={13} /></Button>
                <Button variant="ghost" size="sm" aria-label={`Remove ${w.card?.name} ${wantLabel(w)}`} onClick={() => setConfirm(w)}><Trash2 size={13} /></Button></div>
            </li>))}
        </ul>)}
      {rows.length > 0 && view === "table" && (
        <Table>
          <THead><Th>Card</Th><Th>Version</Th>
            <SortTh label="Price now" num active={f.sort === "value"} dir={dir} onSort={() => sortBy("value")} />
            <SortTh label="Target" num active={f.sort === "target"} dir={dir} onSort={() => sortBy("target")} />
            <Th>Status</Th><Th>Note</Th><Th className="text-right">Actions</Th></THead>
          <tbody>
            {rows.map((w) => (
              <Tr key={w.id}>
                <Td><Link to={`/cards/${encodeURIComponent(w.card_id)}`} className="flex items-center gap-3 hover:text-accent">
                  {w.card?.images?.small && <img src={w.card.images.small} alt="" loading="lazy" className="h-12 object-contain" />}
                  <span><span className="block font-medium">{w.card?.name ?? w.card_id} {w.card?.number && `#${w.card.number}`}</span>
                    <span className="block text-xs text-muted">{w.card?.set?.name}</span></span></Link></Td>
                <Td><Badge tone={w.grading ? "accent" : "neutral"}>{wantLabel(w)}</Badge>{w.variant && <span className="ml-1.5 text-xs text-muted">{w.variant}</span>}</Td>
                <Td num><Price w={w} /></Td>
                <Td num>{w.target_price != null ? money(w.target_price) : <span className="text-muted">—</span>}</Td>
                <Td><Gap w={w} /></Td>
                <Td className="max-w-[16rem] truncate text-muted" title={w.note ?? ""}>{w.note}</Td>
                <Td className="whitespace-nowrap text-right">
                  <Button variant="ghost" size="sm" aria-label={`Edit ${w.card?.name} ${wantLabel(w)}`} onClick={() => setEdit(w)}><Pencil size={13} /></Button>
                  <Button variant="ghost" size="sm" aria-label={`Remove ${w.card?.name} ${wantLabel(w)}`} onClick={() => setConfirm(w)}><Trash2 size={13} /></Button>
                </Td>
              </Tr>))}
          </tbody>
        </Table>)}
      <EditDrawer w={edit} onClose={() => setEdit(null)} />
      <Drawer open={!!confirm} onClose={() => setConfirm(null)} title="Remove from wishlist?">
        <p className="mb-4 text-sm text-muted">{confirm?.card?.name} ({confirm && wantLabel(confirm)}). Its target alert is deleted too.</p>
        <div className="flex gap-2">
          <Button variant="danger" disabled={del.isPending} onClick={() => confirm && del.mutate(confirm.id)}>Remove</Button>
          <Button variant="secondary" onClick={() => setConfirm(null)}>Cancel</Button>
        </div>
      </Drawer>
    </div>);
}
