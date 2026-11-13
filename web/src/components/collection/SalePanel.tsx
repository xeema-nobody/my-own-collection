import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, money, type Listing, type Platform, type SaleStatus, type StackSale } from "../../lib/api";
import { Badge, Button, Field, Input, Select } from "../ui";

export const PLATFORMS: { value: Platform; label: string }[] = [
  { value: "vinted", label: "Vinted" }, { value: "cardmarket", label: "Cardmarket" }, { value: "ebay", label: "eBay" },
  { value: "marktplaats", label: "Marktplaats" }, { value: "other", label: "Other" }];
export const PLATFORM_LABEL = Object.fromEntries(PLATFORMS.map((p) => [p.value, p.label])) as Record<Platform, string>;
export const STATUS_LABEL: Record<SaleStatus, string> = {
  none: "Not for sale", ready: "Ready to list", listed: "Listed", reserved: "Reserved", withdrawn: "Withdrawn" };

/** Small badge for the list; nothing for "not for sale". */
export function SaleBadge({ sale }: { sale?: StackSale | null }) {
  if (!sale || sale.status === "none") return null;
  const where = sale.status === "listed" ? ` · ${sale.listings.map((l) => PLATFORM_LABEL[l.platform]).join(", ")}` : "";
  return <Badge>{STATUS_LABEL[sale.status]}{where}</Badge>;
}

type Draft = { platform: Platform; price: string; date: string; url: string; notes: string; shipping: string };
const blank = (): Draft => ({ platform: "vinted", price: "", date: new Date().toISOString().slice(0, 10), url: "", notes: "", shipping: "" });
const toDraft = (l: Listing): Draft => ({ platform: l.platform, price: String(l.asking_price / 100), date: l.listed_at ?? "", url: l.url ?? "",
  notes: l.notes ?? "", shipping: l.shipping == null ? "" : String(l.shipping / 100) });
const cents = (v: string) => Math.round(+v.replace(",", ".") * 100);

const VINTED_STATE: Record<string, string> = { confirmed: "Waiting for the Claude session", publishing: "Claude is publishing it now", published: "Published", failed: "Failed" };

/** Vinted publish state of one stack + the button that opens the Publish table (the per-item confirm there is the only approval). */
function VintedPublish({ id, link, onPublish }: { id: string; link: string | null; onPublish: (id: string) => void }) {
  const q = useQuery({ queryKey: ["publish-queue", "stack", id], refetchInterval: 5000, queryFn: () => api.publishQueue(undefined, id) });
  const qc = useQueryClient();
  const [ask, setAsk] = useState(false);
  const last = [...(q.data ?? [])].filter((e) => e.state !== "cancelled" && e.state !== "removed").pop();
  const rm = useMutation({
    mutationFn: () => api.publishRemoveVinted(id),
    onSuccess: () => { setAsk(false); qc.invalidateQueries({ queryKey: ["publish-queue"] }); qc.invalidateQueries({ queryKey: ["collection"] }); qc.invalidateQueries({ queryKey: ["sales"] }); },
  });
  const busy = !!last && (last.state === "confirmed" || last.state === "publishing");
  const url = last?.state === "published" ? last.url : link;
  const canRemove = !busy && (!!link || last?.state === "published" || last?.state === "failed");
  return (
    <div className="space-y-1 border-t border-line pt-2" aria-label="Vinted publish">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><span className="font-medium">Vinted</span> <span role="status" className="text-muted">{last ? VINTED_STATE[last.state] : link ? "Listed" : "Not published"}
          {last?.mode === "update" && busy ? " (update)" : ""}</span>
          {url && /^https?:/.test(url) && <> · <a className="text-accent hover:underline" href={url} target="_blank" rel="noreferrer">Vinted item</a></>}</div>
        <Button size="sm" disabled={busy} onClick={() => onPublish(id)}>{link ? "Update on Vinted" : "Publish on Vinted"}</Button>
      </div>
      {canRemove && <div className="flex flex-wrap items-center gap-2">
        {!ask ? <Button variant="secondary" size="sm" onClick={() => setAsk(true)}>Remove Vinted record</Button> : <>
          <span className="text-xs text-warn">Forget this Vinted publication here? Nothing changes on Vinted.</span>
          <Button variant="danger" size="sm" disabled={rm.isPending} onClick={() => rm.mutate()}>Yes, remove</Button>
          <Button variant="ghost" size="sm" onClick={() => setAsk(false)}>Keep</Button></>}
      </div>}
      {rm.error && <p role="alert" className="text-xs text-danger">{(rm.error as Error).message}</p>}
      {last?.state === "failed" && last.error && <p className="text-xs text-danger">{last.error}</p>}
      <p className="text-xs text-muted">Opens the Publish table: you confirm the title, price and photos there; nothing is sent before that.</p>
    </div>);
}

/** Sale state of one stack: status + where it is listed (several platforms allowed). Listings apply to all copies in the stack. */
export default function SalePanel({ id, sale, onPublish }: { id: string; sale?: StackSale | null; onPublish?: (id: string) => void }) {
  const qc = useQueryClient();
  const cur: StackSale = sale ?? { status: "none", listings: [] };
  const [edit, setEdit] = useState(false);
  const [status, setStatus] = useState<SaleStatus>(cur.status);
  const [rows, setRows] = useState<Draft[]>(cur.listings.map(toDraft));
  const m = useMutation({
    mutationFn: () => api.setSale(id, { status, listings: status === "none" ? [] : rows.map((d) => ({
      platform: d.platform, asking_price: cents(d.price), currency: "EUR", listed_at: d.date || null, url: d.url.trim() || null,
      notes: d.notes.trim() || null, shipping: d.shipping.trim() === "" ? null : cents(d.shipping) })) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["collection"] }); qc.invalidateQueries({ queryKey: ["sales"] }); setEdit(false); },
  });
  const upd = (i: number, p: Partial<Draft>) => setRows(rows.map((r, j) => j === i ? { ...r, ...p } : r));
  const valid = status !== "listed" || (rows.length > 0 && rows.every((r) => r.price.trim() !== "" && cents(r.price) >= 0));
  const open = () => { setStatus(cur.status); setRows(cur.listings.map(toDraft)); setEdit(true); };
  return (
    <section className="space-y-2 border-t border-line pt-3 text-sm" aria-label="Sale status">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium">Sale</h3>
        <Button variant="secondary" size="sm" aria-expanded={edit} onClick={() => edit ? setEdit(false) : open()}>{edit ? "Cancel" : "Edit sale"}</Button>
      </div>
      {!edit && <div className="space-y-1 text-muted">
        <div>{STATUS_LABEL[cur.status]}</div>
        {cur.listings.map((l, i) => <div key={i} className="num">{PLATFORM_LABEL[l.platform]} · {money(l.asking_price, l.currency)}/ea
          {l.listed_at ? ` · since ${l.listed_at}` : ""}{l.url && /^https?:/.test(l.url) ? <> · <a className="text-accent hover:underline" href={l.url} target="_blank" rel="noreferrer">link</a></> : null}</div>)}
      </div>}
      {!edit && onPublish && <VintedPublish id={id} link={cur.listings.find((l) => l.platform === "vinted" && l.url)?.url ?? null} onPublish={onPublish} />}
      {edit && <div className="space-y-3">
        <Select aria-label="Sale status" value={status} onChange={(v) => setStatus(v as SaleStatus)}
          options={(Object.keys(STATUS_LABEL) as SaleStatus[]).map((s) => ({ value: s, label: STATUS_LABEL[s] }))} />
        {status === "listed" && <>
          {rows.map((r, i) => <div key={i} className="grid gap-2 rounded border border-line p-2 sm:grid-cols-3">
            <Field label="Platform"><Select aria-label={`Platform ${i + 1}`} value={r.platform} onChange={(v) => upd(i, { platform: v as Platform })} options={PLATFORMS} /></Field>
            <Field label="Asking per copy (EUR)"><Input aria-label={`Asking price ${i + 1}`} type="number" step="0.01" min="0" value={r.price} onChange={(e) => upd(i, { price: e.target.value })} /></Field>
            <Field label="Listed on"><Input aria-label={`Listed on ${i + 1}`} type="date" value={r.date} onChange={(e) => upd(i, { date: e.target.value })} /></Field>
            <Field label="Link"><Input aria-label={`Link ${i + 1}`} value={r.url} placeholder="https://" onChange={(e) => upd(i, { url: e.target.value })} /></Field>
            <Field label="Shipping assumed (EUR)"><Input aria-label={`Shipping ${i + 1}`} type="number" step="0.01" min="0" value={r.shipping} onChange={(e) => upd(i, { shipping: e.target.value })} /></Field>
            <Field label="Notes"><Input aria-label={`Notes ${i + 1}`} maxLength={300} value={r.notes} onChange={(e) => upd(i, { notes: e.target.value })} /></Field>
            <Button type="button" variant="ghost" size="sm" onClick={() => setRows(rows.filter((_, j) => j !== i))}>Remove listing</Button>
          </div>)}
          <Button type="button" variant="secondary" size="sm" onClick={() => setRows([...rows, blank()])}>Add listing</Button>
        </>}
        {status === "none" && cur.listings.length > 0 && <p className="text-xs text-warn">Listings of this stack are cleared.</p>}
        {m.error && <p role="alert" className="text-danger">{(m.error as Error).message}</p>}
        <Button disabled={!valid || m.isPending} onClick={() => m.mutate()}>Save sale</Button>
      </div>}
    </section>);
}
