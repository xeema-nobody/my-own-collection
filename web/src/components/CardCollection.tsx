import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { api, money } from "../lib/api";
import { requestPriceFetch } from "../lib/autoFetch";
import AcquiredForm, { ACQ_TYPES, AcqBadge, acqLabel } from "./AcquiredForm";
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
  const [editing, setEditing] = useState<any>(null);
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
  const editCost = useMutation({ mutationFn: ({ sid, acquired }: { sid: string; acquired: any }) => api.patchStack(sid, { acquired }),
    onSuccess: () => { refresh(); setEditing(null); } });
  const dec = useMutation({
    mutationFn: async ({ sid, del }: { sid: string; del?: boolean }) => { if (del) await api.deleteItem(sid); else await api.removeFromCollection(sid, 1); },
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
              <span className="min-w-0 flex-1 truncate text-muted">{s.variant ? `${s.variant} · ` : ""}{s.language.toUpperCase()}{s.grading?.cert_number ? ` · cert ${s.grading.cert_number}` : ""}{s.grading?.report_url && <> · <a className="text-accent underline" href={s.grading.report_url} target="_blank" rel="noreferrer">Open {s.grading.company} report</a></>}</span>
              <span className="num w-24 text-right" title={v?.needs_price ? "No graded price yet, not counted" : v?.estimated ? "Estimated value of the stack" : "Value of the stack"}>
                {v == null ? "" : v.value == null ? <span className="text-muted">needs price</span> : <>{v.estimated && "≈ "}{money(v.value)}</>}
              </span>
              <span className="flex w-36 items-center justify-end gap-1.5 text-right text-muted">
                <AcqBadge type={s.acquired?.type} />
                <span className="num" title={s.acquired?.source ? `${acqLabel(s.acquired.type)} · ${s.acquired.source}` : undefined}>{s.acquired?.price != null ? `paid ${money(s.acquired.price, s.acquired.currency)}` : ""}</span></span>
              <Button variant="ghost" size="sm" aria-label={`Edit cost of ${stackLabel(s)} stack`} title="Edit cost and how acquired" onClick={() => setEditing(s)}><Pencil size={14} /></Button>
              <Stepper label={`${stackLabel(s)} quantity`} value={s.quantity} min={1} disabled={dec.isPending || inc.isPending} disabledInc={!!s.grading?.cert_number}
                onChange={(n) => (n > s.quantity ? inc.mutate(s) : dec.mutate({ sid: s.id }))} />
              <Button variant="ghost" size="sm" aria-label={`Remove ${stackLabel(s)} stack`} onClick={() => setRemoving(s)}><Trash2 size={14} /></Button>
            </li>);
        })}
      </ul>
      {fetchMsg && <p className="mt-2 text-sm text-muted" role="status">{fetchMsg}</p>}
    </Section>
    <Drawer open={!!editing} onClose={() => setEditing(null)} title={`Cost · ${card.name}${editing ? ` (${stackLabel(editing)})` : ""}`}>
      {editing && <>
        <p className="mb-3 text-sm text-muted">{editing.quantity} {editing.quantity === 1 ? "copy" : "copies"}. The previous value is kept in the stack's edit history.</p>
        <AcquiredForm initial={editing.acquired} qty={editing.quantity} busy={editCost.isPending} onSubmit={(acquired) => editCost.mutate({ sid: editing.id, acquired })} />
        {editCost.error && <p role="alert" className="mt-2 text-sm text-danger">{String((editCost.error as Error).message)}</p>}
      </>}
    </Drawer>
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
  const [f, setF] = useState({ variant: "", language: "en", graded: false, condition: "NM", company: "PSA", grade: "9", cert: "", qty: 1, price: "", acqType: "", date: "", source: "", notes: "" });
  const [more, setMore] = useState(false);
  const [conflict, setConflict] = useState(false);
  const up = (p: Partial<typeof f>) => setF((o) => ({ ...o, ...p }));
  const variant = f.variant || card.variants?.[0] || "";
  const add = useMutation({
    mutationFn: () => api.addToCollection({
      card_id: id, variant: variant || null, language: f.language,
      condition: f.graded ? null : f.condition,
      grading: f.graded ? { company: f.company, grade: +f.grade, cert_number: f.cert || null } : null,
      quantity: f.qty, notes: f.notes || null,
      acquired: f.price || f.acqType ? { type: f.acqType || (+f.price > 0 ? "purchased" : null), price: f.price ? Math.round(+f.price * 100) : null, currency: "EUR",
        date: f.date || null, source: f.source.trim() || null } : null }),
    onSuccess: (r: any) => { setConflict(!!r?.type_conflict); onAdded(); },
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
          <Field label="Acquired how"><Select aria-label="Acquired how" value={f.acqType} allLabel="Not set (Purchased if priced)" onChange={(v) => up({ acqType: v, ...(v === "pulled" && !f.price ? { price: "0" } : {}) })} options={ACQ_TYPES} /></Field>
          <Field label="Date"><Input type="date" aria-label="Date" value={f.date} onChange={(ev) => up({ date: ev.target.value })} /></Field>
          <Field label="Where bought"><Input aria-label="Where bought" value={f.source} onChange={(ev) => up({ source: ev.target.value })} /></Field>
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
          {add.isSuccess && conflict && <span role="status" className="text-sm text-warn">These copies were added to a stack with a different acquisition type or currency: the stack kept its type/price. Use the pencil to fix it.</span>}
        </div>
      </div>
    </Section>);
}
