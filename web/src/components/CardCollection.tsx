import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { api, money } from "../lib/api";
import { requestPriceFetch } from "../lib/autoFetch";
import { Badge, Button, Drawer, Field, Input, SegmentedControl, Section, Select, Stepper } from "./ui";

export const CONDITIONS = ["NM", "LP", "MP", "HP", "DMG"];
const LANGS = ["en", "ja", "es", "it", "fr", "de", "pt", "ko", "zh"];
export const GRADERS = ["PSA", "BGS", "CGC", "SGC", "ACE", "OTHER"];
const GRADES = ["10", "9.5", "9", "8.5", "8", "7.5", "7", "6", "5", "4", "3", "2", "1"];
const opts = (a: string[]) => a.map((v) => ({ value: v, label: v }));
const stackLabel = (s: any) => (s.grading ? `${s.grading.company} ${s.grading.grade}` : s.condition);

/** Owned stacks + the add form of one card. They share the "Saved. Fetching prices…" status. */
export default function CardCollection({ card }: { card: any }) {
  const id: string = card._id ?? card.id;
  const qc = useQueryClient();
  const [fetchMsg, setFetchMsg] = useState("");
  const [removing, setRemoving] = useState<any>(null);
  const owned = useQuery({ queryKey: ["owned-values", id], queryFn: () => api.ownedItems(id) });
  const valueOf = (sid: string) => (owned.data?.items ?? []).find((i: any) => i.id === sid);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["card", id] }); qc.invalidateQueries({ queryKey: ["owned-values", id] }); qc.invalidateQueries({ queryKey: ["collection"] }); };

  // Best-effort: adding never waits for or fails because of the price fetch.
  const autoFetch = async () => {
    setFetchMsg("Saved. Fetching prices…");
    const r = await requestPriceFetch(id);
    qc.invalidateQueries({ queryKey: ["jobs"] });
    setFetchMsg({ started: "Saved. Fetching prices (see Prices > Fetch).", queued: "Saved. Another price fetch is running; this card is queued.",
      offline: "Saved. Prices not fetched: fetcher offline (the stack shows “needs price”).", error: "Saved. Prices not fetched." }[r]);
  };
  const dec = useMutation({
    mutationFn: ({ sid, del }: { sid: string; del?: boolean }) => del ? api.deleteItem(sid) : api.removeFromCollection(sid, 1),
    onSuccess: refresh,
  });
  const inc = useMutation({
    mutationFn: (s: any) => api.addToCollection({ card_id: id, variant: s.variant, language: s.language, condition: s.condition, grading: s.grading, quantity: 1 }),
    onSuccess: () => { refresh(); autoFetch(); },
  });

  return <>
    <Section title={`Owned${card.owned.length ? ` (${card.owned.reduce((n: number, s: any) => n + s.quantity, 0)})` : ""}`}>
      {card.owned.length === 0 && <p className="text-sm text-muted">None yet.</p>}
      <ul className="divide-y divide-line">
        {card.owned.map((s: any) => {
          const v = valueOf(s.id);
          return (
            <li key={s.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
              <Badge tone={s.grading ? "accent" : "neutral"}>{stackLabel(s)}</Badge>
              <span className="min-w-0 flex-1 truncate text-muted">{s.variant ? `${s.variant} · ` : ""}{s.language.toUpperCase()}{s.grading?.cert_number ? ` · cert ${s.grading.cert_number}` : ""}</span>
              <span className="num w-24 text-right" title={v?.needs_price ? "No graded price yet, not counted" : v?.estimated ? "Estimated value of the stack" : "Value of the stack"}>
                {v == null ? "" : v.value == null ? <span className="text-muted">needs price</span> : <>{v.estimated && "≈ "}{money(v.value)}</>}
              </span>
              <span className="num w-20 text-right text-muted">{s.acquired?.price != null ? `paid ${money(s.acquired.price, s.acquired.currency)}` : ""}</span>
              <Stepper label={`${stackLabel(s)} quantity`} value={s.quantity} min={1} disabled={dec.isPending || inc.isPending} disabledInc={!!s.grading?.cert_number}
                onChange={(n) => (n > s.quantity ? inc.mutate(s) : dec.mutate({ sid: s.id }))} />
              <Button variant="ghost" size="sm" aria-label={`Remove ${stackLabel(s)} stack`} onClick={() => setRemoving(s)}><Trash2 size={14} /></Button>
            </li>);
        })}
      </ul>
      {fetchMsg && <p className="mt-2 text-sm text-muted" role="status">{fetchMsg}</p>}
    </Section>
    <Drawer open={!!removing} onClose={() => setRemoving(null)} title="Remove from collection">
      {removing && <div className="space-y-4 text-sm">
        <p>Remove all <span className="num font-medium">{removing.quantity}</span> {removing.quantity === 1 ? "copy" : "copies"} of {card.name} ({stackLabel(removing)})? This deletes the stack.</p>
        <div className="flex gap-2">
          <Button variant="danger" disabled={dec.isPending} onClick={() => dec.mutate({ sid: removing.id, del: true }, { onSuccess: () => setRemoving(null) })}>Remove stack</Button>
          <Button variant="secondary" onClick={() => setRemoving(null)}>Cancel</Button>
        </div>
      </div>}
    </Drawer>
    <AddForm card={card} id={id} onAdded={() => { refresh(); autoFetch(); }} />
  </>;
}

function AddForm({ card, id, onAdded }: { card: any; id: string; onAdded: () => void }) {
  const [f, setF] = useState({ variant: "", language: "en", graded: false, condition: "NM", company: "PSA", grade: "9", cert: "", qty: 1, price: "", notes: "" });
  const [more, setMore] = useState(false);
  const up = (p: Partial<typeof f>) => setF((o) => ({ ...o, ...p }));
  const variant = f.variant || card.variants?.[0] || "";
  const add = useMutation({
    mutationFn: () => api.addToCollection({
      card_id: id, variant: variant || null, language: f.language,
      condition: f.graded ? null : f.condition,
      grading: f.graded ? { company: f.company, grade: +f.grade, cert_number: f.cert || null } : null,
      quantity: f.qty, notes: f.notes || null,
      acquired: f.price ? { price: Math.round(+f.price * 100), currency: "EUR" } : null }),
    onSuccess: onAdded,
  });
  // Value of one copy as it would be counted today (raw: the raw price; graded: that grade's price).
  const est = useQuery({
    queryKey: ["add-estimate", id, f.graded, f.company, f.grade, variant],
    queryFn: () => api.cardCompare(id, { variant: variant || undefined, ...(f.graded ? { company: f.company, grade: +f.grade } : {}) }),
  });
  const e = est.data;
  return (
    <Section title="Add to collection">
      <div className="space-y-3">
        <SegmentedControl label="Copy type" value={f.graded ? "graded" : "raw"} onChange={(v) => up({ graded: v === "graded" })}
          options={[{ value: "raw", label: "Raw" }, { value: "graded", label: "Graded" }]} />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {(card.variants?.length ?? 0) > 1 && <Field label="Variant"><Select aria-label="Variant" value={variant} onChange={(v) => up({ variant: v })} options={opts(card.variants)} /></Field>}
          <Field label="Language"><Select aria-label="Language" value={f.language} onChange={(v) => up({ language: v })} options={opts(LANGS)} /></Field>
          {f.graded ? <>
            <Field label="Grader"><Select aria-label="Grader" value={f.company} onChange={(v) => up({ company: v })} options={opts(GRADERS)} /></Field>
            <Field label="Grade"><Select aria-label="Grade" value={f.grade} onChange={(v) => up({ grade: v })} options={opts(GRADES)} /></Field>
          </> : <Field label="Condition"><SegmentedControl label="Condition" value={f.condition} onChange={(v) => up({ condition: v })} options={CONDITIONS.map((c) => ({ value: c, label: c }))} /></Field>}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Quantity"><div><Stepper label="Quantity to add" value={f.qty} min={1} onChange={(n) => up({ qty: n })} /></div></Field>
          <Field label="Price paid (€)"><div className="w-28"><Input type="number" step="0.01" min="0" value={f.price} onChange={(ev) => up({ price: ev.target.value })} /></div></Field>
          <Button variant="ghost" size="sm" aria-expanded={more} onClick={() => setMore(!more)}>{more ? "Fewer options" : "More"}</Button>
        </div>
        {more && <div className="grid gap-3 sm:grid-cols-2">
          {f.graded && <Field label="Cert #"><Input value={f.cert} onChange={(ev) => up({ cert: ev.target.value })} /></Field>}
          <Field label="Notes"><Input value={f.notes} onChange={(ev) => up({ notes: ev.target.value })} /></Field>
        </div>}
        <div className="flex flex-wrap items-center gap-3 border-t border-line pt-3">
          <Button disabled={add.isPending} onClick={() => add.mutate()}>Add {f.qty > 1 ? `${f.qty} copies` : "to collection"}</Button>
          <span className="text-sm text-muted" data-testid="estimate">
            {est.isLoading ? "Estimating…" : e?.value != null
              ? <>Estimated <span className="num font-medium text-fg">{e.estimated && "≈ "}{money(e.value * f.qty)}</span>{f.qty > 1 && <> ({money(e.value)} each)</>}</>
              : f.graded ? "No price for this grade yet; it is fetched after adding and not counted until then." : "No price yet; it is fetched after adding."}
          </span>
          {add.error && <span role="alert" className="text-sm text-danger">{String(add.error)}</span>}
          {add.isSuccess && <span className="text-sm text-ok">Added</span>}
        </div>
      </div>
    </Section>);
}
