import { useState } from "react";
import { money, type Acquired, type ScanCard } from "../../lib/api";
import { CONDITIONS, CONDITION_HELP, LANGUAGES, type Choice } from "../../lib/scan";
import AcquiredForm from "../AcquiredForm";
import { Badge, Button, Field, Select, Stepper } from "../ui";

/** Details for the picked version: condition, language, quantity, optional cost. Remembers the last choice. */
export default function AddSheet({ card, initial, busy, error, onBack, onAdd }: {
  card: ScanCard; initial: Choice; busy?: boolean; error?: string | null; onBack: () => void;
  onAdd: (body: { card_id: string; variant: string | null; language: string; condition: string; quantity: number; acquired?: Acquired }, choice: Choice) => void;
}) {
  const [condition, setCondition] = useState(initial.condition);
  const [language, setLanguage] = useState(initial.language);
  const [qty, setQty] = useState(1);
  const [variant, setVariant] = useState<string | null>(card.variants[0] ?? null);
  const [acq, setAcq] = useState<Acquired | null>(initial.acquired);
  const same = card.owned.find((o) => !o.grading && o.condition === condition && o.language === language && (o.variant ?? null) === variant);
  const hasAcq = acq && Object.values(acq).some((v) => v != null && v !== "");
  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        {card.image && <img src={card.image} alt="" className="w-24 rounded" />}
        <div className="space-y-1 text-sm">
          <div className="text-base font-semibold">{card.name}</div>
          <div className="text-muted">{card.set.name}{card.year ? ` · ${card.year}` : ""} · #{card.number}{card.printed_total ? `/${card.printed_total}` : ""}</div>
          {card.rarity && <Badge>{card.rarity}</Badge>}
          <div className="num font-semibold">{money(card.price)}</div>
          <Button variant="ghost" size="sm" onClick={onBack}>Pick another version</Button>
        </div>
      </div>

      {card.variants.length > 1 && <Field label="Which print">
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Which print">
          {card.variants.map((v) => <Button key={v} variant={v === variant ? "primary" : "secondary"} role="radio" aria-checked={v === variant} onClick={() => setVariant(v)}>{v === "reverseHolofoil" ? "Reverse holo" : v === "holofoil" ? "Holo" : v}</Button>)}
        </div></Field>}

      <Field label="Condition">
        <div className="grid grid-cols-5 gap-1.5" role="radiogroup" aria-label="Condition">
          {CONDITIONS.map((c) => <Button key={c} variant={c === condition ? "primary" : "secondary"} className="py-3 text-base" role="radio" aria-checked={c === condition} onClick={() => setCondition(c)}>{c}</Button>)}
        </div>
        <p className="mt-1 text-xs text-muted">{CONDITION_HELP[condition]}</p>
      </Field>

      <div className="flex items-end gap-4">
        <Field label="Language"><Select aria-label="Language" value={language} onChange={setLanguage} options={LANGUAGES.map(([value, label]) => ({ value, label }))} /></Field>
        <Field label="Copies"><Stepper label="copies" value={qty} min={1} max={99} onChange={setQty} /></Field>
      </div>

      {same && <p className="rounded bg-ok/15 px-3 py-2 text-sm text-ok">You already own {same.quantity} in this condition: {qty === 1 ? "this adds one more copy to that stack" : `this adds ${qty} copies to that stack`} ({same.quantity + qty} total).</p>}

      <details className="rounded-lg border border-line bg-surface p-3">
        <summary className="cursor-pointer text-sm font-medium">Cost and how you got it{hasAcq ? " (set)" : " (optional)"}</summary>
        <div className="pt-3"><AcquiredForm initial={acq} qty={qty} hideSubmit onChange={setAcq} /></div>
      </details>

      {error && <p role="alert" className="rounded bg-danger/15 px-3 py-2 text-sm text-danger">{error}</p>}
      <Button className="w-full py-3 text-base" disabled={busy}
        onClick={() => onAdd({ card_id: card.id, variant, language, condition, quantity: qty, ...(hasAcq ? { acquired: acq as Acquired } : {}) }, { condition, language, acquired: hasAcq ? acq : null })}>
        {busy ? "Adding…" : `Add ${qty} to collection`}</Button>
    </div>);
}
