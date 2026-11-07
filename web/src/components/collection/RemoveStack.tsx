import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type ExitReason } from "../../lib/api";
import { Button, Field, Input, SegmentedControl } from "../ui";

const REASONS: { value: ExitReason; label: string }[] = [
  { value: "sold", label: "Sold" }, { value: "gifted", label: "Gifted" }, { value: "removed", label: "Just remove" }];
const HINT: Record<ExitReason, string> = {
  sold: "Keeps a record with the sale price.", gifted: "Keeps a record, no money.", removed: "Keeps a record (mistake, lost, other)." };

/** Take copies of a stack out of the collection. Always leaves a history row, so nothing disappears silently. */
export default function RemoveStack({ id, quantity, name, onDone }: { id: string; quantity: number; name: string; onDone?: () => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ExitReason>("sold");
  const [qty, setQty] = useState("1");
  const [price, setPrice] = useState("");
  const [note, setNote] = useState("");
  const n = Math.min(Math.max(parseInt(qty, 10) || 1, 1), quantity);
  const m = useMutation({
    mutationFn: () => api.removeFromCollection(id, n, {
      reason, note: note.trim() || null, price: reason === "sold" && price.trim() !== "" ? Math.round(+price * 100) : null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["collection"] }); qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["exits"] }); setOpen(false); onDone?.(); },
  });
  if (!open) return <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>Sell / remove</Button>;
  return (
    <form className="space-y-3 rounded border border-line p-3" aria-label="Remove from collection"
      onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
      <div className="text-sm font-medium">Remove {name}</div>
      <SegmentedControl label="Reason" value={reason} onChange={setReason} options={REASONS} />
      <p className="text-xs text-muted">{HINT[reason]}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={`Copies (of ${quantity})`}>
          <Input aria-label="Copies" type="number" min={1} max={quantity} value={qty} onChange={(e) => setQty(e.target.value)} />
        </Field>
        {reason === "sold" && <Field label="Sold for, per copy (EUR, optional)">
          <Input aria-label="Sale price" type="number" step="0.01" min="0" value={price} onChange={(e) => setPrice(e.target.value)} />
        </Field>}
      </div>
      <Field label="Note (optional)"><Input aria-label="Note" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Who / where" /></Field>
      {n >= quantity && <p className="text-xs text-warn">This removes the whole stack.</p>}
      {m.error && <p role="alert" className="text-sm text-danger">{(m.error as Error).message}</p>}
      <div className="flex gap-2">
        <Button type="submit" disabled={m.isPending}>{reason === "sold" ? "Mark sold" : reason === "gifted" ? "Mark gifted" : "Remove"}{n > 1 ? ` (${n})` : ""}</Button>
        <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </form>);
}

export const exitLabel = (r: ExitReason) => REASONS.find((x) => x.value === r)?.label ?? r;

