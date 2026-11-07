import { useState } from "react";
import type { AcqType, Acquired, AcquiredPatch } from "../lib/api";
import { Badge, Button, Field, Input, SegmentedControl, Select } from "./ui";

export const ACQ_TYPES: { value: AcqType; label: string }[] = [
  { value: "purchased", label: "Purchased" }, { value: "pulled", label: "Pulled" }, { value: "traded", label: "Traded" },
  { value: "gift", label: "Gift" }, { value: "other", label: "Other" },
];
const CURRENCIES = ["EUR", "USD", "GBP", "JPY"].map((c) => ({ value: c, label: c }));

export const acqLabel = (t: string | null | undefined) => ACQ_TYPES.find((x) => x.value === t)?.label ?? "Not set";

/** Small badge for a stack's acquisition type; nothing when not set. */
export function AcqBadge({ type }: { type?: string | null }) {
  return type ? <Badge tone={type === "pulled" ? "accent" : "neutral"}>{acqLabel(type)}</Badge> : null;
}

type State = { type: string; price: string; total: boolean; currency: string; date: string; source: string };

/** Form state -> patch. Edit: every field is sent (blank = clear). Bulk: blank fields are left out (= keep). */
export function buildPatch(f: State, qty: number, bulk: boolean): AcquiredPatch {
  const out: AcquiredPatch = {};
  const euros = f.price.trim() === "" ? null : Math.round(+f.price * 100);
  const perCopy = euros == null ? null : f.total && !bulk ? Math.round(euros / Math.max(qty, 1)) : euros;
  if (!bulk || f.type) out.type = (f.type || null) as AcqType | null;
  if (!bulk || euros != null) out.price = perCopy;
  if (!bulk || f.currency) out.currency = f.currency || "EUR";
  if (!bulk || f.date) out.date = f.date || null;
  if (!bulk || f.source.trim()) out.source = f.source.trim() || null;
  return out;
}

/** Edit cost + acquisition type of a stack (`bulk` = several stacks: blank keeps the current value). */
export default function AcquiredForm({ initial, qty = 1, bulk = false, busy, submitLabel = "Save", onSubmit, onChange, hideSubmit }: {
  initial?: Acquired | null; qty?: number; bulk?: boolean; busy?: boolean; submitLabel?: string; onSubmit?: (p: AcquiredPatch) => void;
  /** Called with the current patch on every edit (and once on mount): lets a parent own the submit button. */
  onChange?: (p: AcquiredPatch) => void; hideSubmit?: boolean;
}) {
  const [f, setF] = useState<State>({
    type: initial?.type ?? "", price: initial?.price != null ? String(initial.price / 100) : "", total: false,
    currency: bulk ? "" : initial?.currency ?? "EUR", date: initial?.date ?? "", source: initial?.source ?? "" });
  const up = (p: Partial<State>) => {
    const n = { ...f, ...p };
    setF(n);
    onChange?.(buildPatch(n, qty, bulk));
  };
  const total = f.total && !bulk;
  const perCopy = total && f.price.trim() !== "" ? Math.round(+f.price * 100 / Math.max(qty, 1)) : null;
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); onSubmit?.(buildPatch(f, qty, bulk)); }}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Acquired how">
          <Select aria-label="Acquired how" value={f.type} allLabel={bulk ? "Keep current" : "Not set"}
            onChange={(v) => up({ type: v, ...(v === "pulled" && f.price.trim() === "" && !bulk ? { price: "0" } : {}) })} options={ACQ_TYPES} />
        </Field>
        <Field label="Currency">
          <Select aria-label="Currency" value={f.currency} allLabel={bulk ? "Keep current" : undefined} onChange={(v) => up({ currency: v })} options={CURRENCIES} />
        </Field>
        <Field label={total ? `Total paid for ${qty} ${qty === 1 ? "copy" : "copies"}` : bulk ? "Price per copy (blank = keep)" : "Price per copy"}>
          <Input aria-label="Price" type="number" step="0.01" min="0" value={f.price} onChange={(e) => up({ price: e.target.value })} />
        </Field>
        <Field label="Date">
          <Input aria-label="Date" type="date" value={f.date} onChange={(e) => up({ date: e.target.value })} />
        </Field>
        <Field label="Where bought" className="sm:col-span-2">
          <Input aria-label="Where bought" placeholder="Cardmarket, local shop…" value={f.source} onChange={(e) => up({ source: e.target.value })} />
        </Field>
      </div>
      {!bulk && qty > 1 && <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
        <SegmentedControl label="Price entry" value={f.total ? "total" : "copy"} onChange={(v) => up({ total: v === "total" })}
          options={[{ value: "copy", label: "Per copy" }, { value: "total", label: `Total for ${qty}` }]} />
        <span>{perCopy != null ? `= ${(perCopy / 100).toFixed(2)} per copy` : "Different prices per copy: enter the total, the average is stored."}</span>
      </div>}
      {bulk && <p className="text-xs text-muted">Only the fields you fill in change; the rest stay as they are on each stack. Price is per copy.</p>}
      {!hideSubmit && <Button type="submit" disabled={busy}>{submitLabel}</Button>}
    </form>);
}
