import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, money, type PackItem, type PackStrategy, type VintedCondition, type VintedParcel } from "../../lib/api";
import { QueueList } from "./PublishQueue";
import { Button, Drawer, Field, Input, Select, Skeleton } from "../ui";

type Edit = { title?: string; description?: string; price?: string; condition?: VintedCondition; parcel?: VintedParcel };
const CONDITIONS = (["New with tags", "New without tags", "Very good", "Good", "Satisfactory"] as const).map((c) => ({ value: c, label: c }));
const PARCELS = [{ value: "small", label: "Small (envelope)" }, { value: "medium", label: "Medium (shoebox)" }, { value: "large", label: "Large" }];
const ACTIVE = ["confirmed", "publishing"];
const STRATEGIES = [{ value: "market", label: "Match market" }, { value: "under", label: "Slightly under market" }, { value: "floor", label: "Floor (lowest source)" }];
const PLATFORMS = [{ value: "vinted", label: "Vinted" }, { value: "cardmarket", label: "Cardmarket" }];

const cents = (s: string) => { const n = Math.round(parseFloat(s.replace(",", ".")) * 100); return Number.isFinite(n) && n >= 0 ? n : null; };
const euros = (c: number | null) => (c === null ? "" : (c / 100).toFixed(2));
const copy = (t: string) => navigator.clipboard?.writeText(t);

/** Listing pack (roadmap 6c): editable title / description / price per stack. Nothing is published; "Mark as Listed" saves the
 *  listing on the stack through the normal sale endpoint. */
export default function ListingPackDrawer({ ids, open, onClose }: { ids: string[]; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [platform, setPlatform] = useState<"vinted" | "cardmarket">("vinted");
  const [strategy, setStrategy] = useState<PackStrategy>("market");
  const [pct, setPct] = useState("5");
  const pctN = Math.min(90, Math.max(0, parseInt(pct, 10) || 0));
  const [edits, setEdits] = useState<Record<string, Edit>>({});
  const pack = useQuery({ queryKey: ["listing-pack", ids, platform, strategy, pctN], enabled: open && ids.length > 0,
    queryFn: () => api.listingPack({ ids, platform, strategy, pct: pctN }) });
  useEffect(() => setEdits({}), [pack.data]);
  const set = (id: string, e: Edit) => setEdits((x) => ({ ...x, [id]: { ...x[id], ...e } }));
  const priceOf = (p: PackItem) => { const e = edits[p.item_id]?.price; return e !== undefined ? cents(e) : p.price; };

  const queue = useQuery({ queryKey: ["publish-queue"], enabled: open && platform === "vinted", refetchInterval: open ? 5000 : false,
    queryFn: () => api.publishQueue(["confirmed", "publishing", "failed", "published"]) });
  const entryOf = (id: string) => queue.data?.filter((q) => q.item_id === id && ACTIVE.includes(q.state))[0];
  const confirm = useMutation({
    mutationFn: (p: PackItem) => {
      const e = edits[p.item_id] ?? {};
      return api.publishConfirm([{ item_id: p.item_id, title: e.title ?? p.title, description: e.description ?? p.description, price: priceOf(p)!, currency: p.currency,
        condition: e.condition ?? p.vinted_condition, parcel: e.parcel ?? p.vinted_parcel }]);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["publish-queue"] }),
  });
  const act = useMutation({ mutationFn: ({ id, a }: { id: string; a: "cancel" | "retry" | "release" }) => api.publishAct(id, a),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["publish-queue"] }) });
  const refused = confirm.data?.results.find((r) => !r.ok)?.error;

  const listed = useMutation({
    mutationFn: async () => {
      const day = new Date().toISOString().slice(0, 10);
      const rows = (pack.data?.items ?? []).filter((p) => priceOf(p) !== null && !(platform === "cardmarket" && p.warnings.some((w) => w.startsWith("slab"))));
      let done = 0;
      for (const p of rows) {
        const keep = (p.sale?.listings ?? []).filter((l) => l.platform !== platform);  // other platforms stay, this one is replaced
        await api.setSale(p.item_id, { status: "listed", listings: [...keep, { platform, asking_price: priceOf(p)!, currency: p.currency, listed_at: day }] });
        done++;
      }
      return done;
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["collection"] }); qc.invalidateQueries({ queryKey: ["sales"] }); qc.invalidateQueries({ queryKey: ["dashboard"] }); },
  });

  return (
    <Drawer open={open} onClose={onClose} title={`Listing pack · ${ids.length} stack${ids.length === 1 ? "" : "s"}`}>
      <div className="space-y-4 text-sm">
        <div className="grid gap-3 sm:grid-cols-3">
          <Select aria-label="Platform" value={platform} onChange={(v) => setPlatform(v as typeof platform)} options={PLATFORMS} />
          <Select aria-label="Price strategy" value={strategy} onChange={(v) => setStrategy(v as PackStrategy)} options={STRATEGIES} />
          {strategy === "under" && <Field label="Percent under market"><Input aria-label="Percent under" inputMode="numeric" value={pct} onChange={(e) => setPct(e.target.value)} /></Field>}
        </div>
        {pack.isLoading && <Skeleton className="h-40 w-full" />}
        {pack.error && <p role="alert" className="text-danger">{String((pack.error as Error).message)}</p>}
        {pack.data?.missing.length ? <p className="text-warn">{pack.data.missing.length} selected stack(s) no longer exist.</p> : null}
        {pack.data?.items.map((p, n) => {
          const e = edits[p.item_id] ?? {};
          const title = e.title ?? p.title, desc = e.description ?? p.description;
          return (
            <section key={p.item_id} aria-label={`Pack ${n + 1}`} className="space-y-2 rounded-lg border border-line p-3">
              <Field label="Title"><Input aria-label={`Title ${n + 1}`} value={title} onChange={(ev) => set(p.item_id, { title: ev.target.value })} /></Field>
              <Field label="Description">
                <textarea aria-label={`Description ${n + 1}`} rows={6} value={desc} onChange={(ev) => set(p.item_id, { description: ev.target.value })}
                  className="w-full rounded border border-line bg-surface px-2.5 py-1.5 text-sm text-fg" />
              </Field>
              <Field label={`Asking price (${p.currency}) per copy`}>
                <Input aria-label={`Price ${n + 1}`} inputMode="decimal" value={e.price ?? euros(p.price)} placeholder="no price" onChange={(ev) => set(p.item_id, { price: ev.target.value })} />
              </Field>
              {platform === "vinted" && p.market_price != null && p.market_price !== priceOf(p) && (
                <p className="flex flex-wrap items-center gap-2 text-xs text-muted">Market suggests {money(p.market_price, p.currency)}
                  <Button size="sm" variant="ghost" onClick={() => set(p.item_id, { price: euros(p.market_price!) })}>Use market price</Button></p>)}
              {platform === "vinted" && p.queued && <p className="text-xs text-accent">Already queued: showing the queued price and text ({money(p.price ?? 0, p.currency)}), not today's market price.</p>}
              {platform === "vinted" && p.stored && !p.queued && <p className="text-xs text-muted">Prefilled from what you last published on Vinted.</p>}
              {platform === "vinted" && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Select aria-label={`Condition ${n + 1}`} value={e.condition ?? p.vinted_condition} onChange={(v) => set(p.item_id, { condition: v as VintedCondition })} options={CONDITIONS} />
                  <Select aria-label={`Parcel ${n + 1}`} value={e.parcel ?? p.vinted_parcel} onChange={(v) => set(p.item_id, { parcel: v as VintedParcel })} options={PARCELS} />
                </div>)}
              {p.warnings.map((w) => <p key={w} className="text-xs text-warn">{w}</p>)}
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" onClick={() => copy(title)}>Copy title</Button>
                <Button size="sm" variant="secondary" onClick={() => copy(desc)}>Copy description</Button>
                <Button size="sm" variant="secondary" onClick={() => { const c = priceOf(p); if (c !== null) copy(euros(c)); }}>Copy price {priceOf(p) !== null ? money(priceOf(p)!, p.currency) : ""}</Button>
                {p.photos.length > 0 && <a className="inline-flex items-center rounded border border-line px-2 py-1 text-xs hover:bg-surface-2" href={api.photosZipUrl(p.item_id)}>Photos ({p.photos.length}) .zip</a>}
              </div>
              {platform === "vinted" && (
                <div className="flex flex-wrap items-center gap-3 border-t border-line pt-2">
                  {entryOf(p.item_id)
                    ? <span role="status" className="text-xs text-accent">{entryOf(p.item_id)!.state === "publishing" ? "Claude is publishing this now" : "Confirmed: waiting for the Claude session"}</span>
                    : <Button size="sm" disabled={confirm.isPending || priceOf(p) === null || p.photos.length === 0 || !title.trim() || !desc.trim()}
                        onClick={() => confirm.mutate(p)}>{p.vinted_url ? "Confirm update on Vinted" : "Confirm publish on Vinted"}</Button>}
                  <span className="text-xs text-muted">{p.vinted_url ? "Has a Vinted link: updates that item's price and text." : "New Vinted item."}</span>
                </div>)}
            </section>);
        })}
        {refused && <p role="alert" className="text-danger">{refused}</p>}
        {confirm.error && <p role="alert" className="text-danger">{String((confirm.error as Error).message)}</p>}
        {platform === "vinted" && queue.data && queue.data.length > 0 && <QueueList entries={queue.data} busy={act.isPending} onAct={(id, a) => act.mutate({ id, a })} />}
        {pack.data && pack.data.items.length > 0 && (
          <div className="flex flex-wrap items-center gap-3">
            {platform === "cardmarket" && <a className="inline-flex items-center rounded border border-line px-3 py-1.5 hover:bg-surface-2" href={api.listingPackCsvUrl(ids, strategy, pctN)}>Download CSV sheet</a>}
            <Button disabled={listed.isPending} onClick={() => listed.mutate()}>Mark as Listed on {platform === "vinted" ? "Vinted" : "Cardmarket"}</Button>
            <span className="text-xs text-muted">Saves the asking prices as listings. Nothing is published for you; other platforms' listings stay.</span>
          </div>)}
        {listed.error && <p role="alert" className="text-danger">{String((listed.error as Error).message)}</p>}
        {listed.isSuccess && <p role="status" className="text-ok">Marked {listed.data} stack{listed.data === 1 ? "" : "s"} as Listed.</p>}
      </div>
    </Drawer>);
}
