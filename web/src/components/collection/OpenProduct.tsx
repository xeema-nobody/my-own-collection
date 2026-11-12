import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type OpenResult, type PullIn } from "../../lib/api";
import { errorText } from "../QueryState";
import { Button, Combobox, Field, Input } from "../ui";

type Staged = PullIn & { label: string };
const today = () => new Date().toISOString().slice(0, 10);

/** "I opened this" for a sealed stack: takes units out (history row 'Opened'), stores the opening, adds the pulled
 *  cards as acquisition 'pulled' (no cost, out of P/L, in collection value). Pulls can be added again afterwards. */
export default function OpenProduct({ id, quantity, name, onDone }: { id: string; quantity: number; name: string; onDone?: () => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [qty, setQty] = useState("1");
  const [date, setDate] = useState(today());
  const [extras, setExtras] = useState("");
  const [note, setNote] = useState("");
  const [staged, setStaged] = useState<Staged[]>([]);
  const [pickId, setPickId] = useState("");
  const [pickLabel, setPickLabel] = useState("");
  const [result, setResult] = useState<OpenResult | null>(null);
  const [added, setAdded] = useState(0);
  const n = Math.min(Math.max(parseInt(qty, 10) || 1, 1), quantity);
  const refresh = () => ["collection", "dashboard", "exits", "openings"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const fetchCards = async (q: string, page: number) => {
    const r = await api.cards({ q, page, page_size: 20 });
    return { options: r.items.map((c: any) => ({ value: c.id, label: `${c.name} · ${c.set?.name ?? ""} #${c.number}` })), more: r.page * r.page_size < r.total };
  };
  const stage = (card_id: string, label: string) => {
    if (!card_id) return;
    setStaged((s) => s.some((x) => x.card_id === card_id) ? s.map((x) => x.card_id === card_id ? { ...x, quantity: x.quantity + 1 } : x)
      : [...s, { card_id, label, quantity: 1, condition: "NM", language: "en" }]);
    setPickId(""); setPickLabel("");
  };
  const pulls = (): PullIn[] => staged.map(({ label: _l, ...p }) => p);
  const reset = () => { setStaged([]); setExtras(""); setNote(""); setQty("1"); };
  const openM = useMutation({
    mutationFn: () => api.openProduct(id, { quantity: n, date, note: note.trim() || null, extras: extras.trim() || null, pulled: pulls() }),
    onSuccess: (r) => { setResult(r); setAdded(r.pulled.length); reset(); refresh(); },
  });
  const moreM = useMutation({
    mutationFn: () => api.addOpeningPulls(result!.opening_id, pulls()),
    onSuccess: (r) => { setAdded((a) => a + r.pulled.length); setStaged([]); refresh(); },
  });
  const list = (
    <div className="space-y-2">
      <Field label="Pulled cards (search by name)">
        <Combobox aria-label="Pulled card" cacheKey="open-pulls" value={pickId} selectedLabel={pickLabel} placeholder="Add a pulled card…"
          fetchPage={fetchCards} onChange={(v, l) => stage(v, l)} />
      </Field>
      {staged.length > 0 && <ul className="divide-y divide-line text-sm">
        {staged.map((p) => (
          <li key={p.card_id} className="flex items-center justify-between gap-2 py-1">
            <span className="truncate">{p.label}</span>
            <span className="flex shrink-0 items-center gap-2">
              <Input aria-label={`Copies of ${p.label}`} className="w-16" type="number" min={1} max={99} value={p.quantity}
                onChange={(e) => setStaged((s) => s.map((x) => x.card_id === p.card_id ? { ...x, quantity: Math.max(1, parseInt(e.target.value, 10) || 1) } : x))} />
              <Button size="sm" variant="ghost" type="button" onClick={() => setStaged((s) => s.filter((x) => x.card_id !== p.card_id))}>Remove</Button>
            </span>
          </li>))}
      </ul>}
      <p className="text-xs text-muted">Pulled cards carry no cost: out of P/L, counted in collection value.</p>
    </div>);
  if (result) return (
    <div className="space-y-2 rounded border border-line p-3 text-sm" role="status">
      <div>Opened {result.opened} × {name}{result.stack_deleted ? " (stack is gone)" : `, ${result.left} left`}. {added} pulled card{added === 1 ? "" : "s"} added.</div>
      {list}
      {result.pulled.some((p) => p.type_conflict) && <p className="text-xs text-warn">A pulled card joined a stack with another acquisition type; the old cost was kept.</p>}
      {moreM.error && <p role="alert" className="text-danger">{errorText(moreM.error)}</p>}
      <div className="flex gap-2">
        <Button size="sm" disabled={!staged.length || moreM.isPending} onClick={() => moreM.mutate()}>Add pulled cards</Button>
        <Button size="sm" variant="secondary" onClick={() => { setResult(null); setStaged([]); setOpen(false); onDone?.(); }}>Done</Button>
      </div>
    </div>);
  if (!open) return <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>Open product</Button>;
  return (
    <form className="space-y-3 rounded border border-line p-3" aria-label="Open product"
      onSubmit={(e) => { e.preventDefault(); openM.mutate(); }}>
      <div className="text-sm font-medium">Open {name}</div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={`Units opened (of ${quantity})`}><Input aria-label="Units opened" type="number" min={1} max={quantity} value={qty} onChange={(e) => setQty(e.target.value)} /></Field>
        <Field label="Date"><Input aria-label="Date opened" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
      </div>
      {list}
      <Field label="Extras (code card, coin, sleeves…)"><Input aria-label="Extras" maxLength={1000} value={extras} onChange={(e) => setExtras(e.target.value)} /></Field>
      <Field label="Note (optional)"><Input aria-label="Note" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      {n >= quantity && <p className="text-xs text-warn">This opens the whole stack.</p>}
      {openM.error && <p role="alert" className="text-sm text-danger">{errorText(openM.error)}</p>}
      <div className="flex gap-2">
        <Button type="submit" disabled={openM.isPending}>Mark opened{n > 1 ? ` (${n})` : ""}</Button>
        <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </form>);
}
