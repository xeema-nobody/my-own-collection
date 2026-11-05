import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { api, money, type WishEntry } from "../lib/api";
import { eurosToCents, filterWishes, wantLabel, type WishFilter } from "../lib/wishlist";
import BulkFetch from "../components/BulkFetch";
import { QueryError } from "../components/QueryState";
import { Badge, Button, Card, Checkbox, Chip, Drawer, EmptyState, Field, Input, Kpi, Skeleton, Table, THead, Td, Th, Tr } from "../components/ui";

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

export default function Wishlist() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["wishlist"], queryFn: () => api.wishlist() });
  const [filter, setFilter] = useState<WishFilter>("all");
  const [edit, setEdit] = useState<WishEntry | null>(null);
  const [confirm, setConfirm] = useState<WishEntry | null>(null);
  const del = useMutation({
    mutationFn: (id: string) => api.removeWish(id),
    onSuccess: () => { setConfirm(null); qc.invalidateQueries({ queryKey: ["wishlist"] }); qc.invalidateQueries({ queryKey: ["alerts"] }); },
  });
  const fresh = useQuery({ queryKey: ["wishlist", "prices"], queryFn: api.wishlistPrices });
  const all = q.data ?? [];
  const rows = filterWishes(all, filter);
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
      </div>
      <QueryError q={q} label="Wishlist" />
      {q.isLoading && <Skeleton className="h-40" />}
      {q.data && all.length === 0 && <EmptyState title="Nothing on your wishlist">Open a card and use “Add to wishlist”.</EmptyState>}
      {q.data && all.length > 0 && rows.length === 0 && <EmptyState title="No entries match this filter" />}
      {rows.length > 0 && (
        <Table>
          <THead><Th>Card</Th><Th>Version</Th><Th num>Price now</Th><Th num>Target</Th><Th>Status</Th><Th>Note</Th><Th className="text-right">Actions</Th></THead>
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
