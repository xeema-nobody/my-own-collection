import { useState } from "react";
import { money, type Acquired, type ScanCard, type ScanSlab } from "../../lib/api";
import { CONDITIONS, CONDITION_HELP, GRADERS, LANGUAGES, parseSlabGrade, type Choice } from "../../lib/scan";
import AcquiredForm from "../AcquiredForm";
import { Badge, Button, Field, Input, Select, Stepper } from "../ui";

/** Details for the picked version: condition, language, quantity, optional cost. Remembers the last choice. */
export type SlabGrading = { company: string; grade: number; cert_number: string | null; grader_name?: string };
export default function AddSheet({ card, initial, busy, error, slab, onBack, onAdd }: {
  card: ScanCard; initial: Choice; busy?: boolean; error?: string | null; slab?: ScanSlab | null; onBack: () => void;
  onAdd: (body: { card_id: string; variant: string | null; language: string; condition?: string; grading?: SlabGrading; quantity: number; acquired?: Acquired }, choice: Choice) => void;
}) {
  // A slab (graded card): `slab` is what the label read (may be empty when the user said "slab" themselves).
  const [isSlab, setIsSlab] = useState(!!slab);
  const [grader, setGrader] = useState(slab?.grader ?? "");
  const [grade, setGrade] = useState(slab?.grade != null ? String(slab.grade) : "");
  const [cert, setCert] = useState(slab?.cert ?? "");
  const [graderName, setGraderName] = useState("");
  const [condition, setCondition] = useState(initial.condition);
  const [language, setLanguage] = useState(initial.language);
  const [qty, setQty] = useState(1);
  const [variant, setVariant] = useState<string | null>(card.variants[0] ?? null);
  const [acq, setAcq] = useState<Acquired | null>(initial.acquired);
  const certTrim = cert.replace(/\s+/g, "");
  const slabGrade = parseSlabGrade(grade);
  const slabOk = grader !== "" && slabGrade !== null && (grader !== "OTHER" || graderName.trim() !== "");
  const sameSlab = isSlab && certTrim !== "" && card.owned.some((o) => (o.grading as { cert_number?: string } | null)?.cert_number === certTrim);
  const same = isSlab ? undefined : card.owned.find((o) => !o.grading && o.condition === condition && o.language === language && (o.variant ?? null) === variant);
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

      <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Raw or slab">
        <Button variant={isSlab ? "secondary" : "primary"} role="radio" aria-checked={!isSlab} onClick={() => setIsSlab(false)}>Raw card</Button>
        <Button variant={isSlab ? "primary" : "secondary"} role="radio" aria-checked={isSlab} onClick={() => setIsSlab(true)}>Slab (graded)</Button>
      </div>

      {isSlab && <div className="space-y-3 rounded-lg border border-line bg-surface p-3">
        {slab?.grader && slab.grader_seen === false && <p className="text-xs text-muted">The grader is a guess from the label layout: check it.</p>}
        {!slab?.grader && !slab?.grade && !slab?.cert && <p className="text-xs text-muted">The label could not be read: type it from the slab.</p>}
        <Field label="Grader">
          <div className="grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Grader">
            {GRADERS.map(([v, l]) => <Button key={v} variant={v === grader ? "primary" : "secondary"} role="radio" aria-checked={v === grader} onClick={() => setGrader(v)}>{l}</Button>)}
          </div>
        </Field>
        {grader === "OTHER" && <Field label="Grader name"><Input aria-label="Grader name" placeholder="e.g. TAG, Cardgrader" maxLength={40} value={graderName} onChange={(e) => setGraderName(e.target.value)} /></Field>}
        <div className="flex gap-3">
          <Field label="Grade"><Input aria-label="Grade" inputMode="decimal" placeholder="9.5" value={grade} onChange={(e) => setGrade(e.target.value)} /></Field>
          <Field label="Cert number"><Input aria-label="Cert number" inputMode="numeric" placeholder="optional" maxLength={20} value={cert} onChange={(e) => setCert(e.target.value)} /></Field>
        </div>
        {grade.trim() !== "" && slabGrade === null && <p className="text-xs text-danger">Grade is 1 to 10, in half steps.</p>}
        <p className="text-xs text-muted">A slab is valued at its graded price only. Without one it stays "needs price", never the raw price.</p>
      </div>}

      {!isSlab && <Field label="Condition">
        <div className="grid grid-cols-5 gap-1.5" role="radiogroup" aria-label="Condition">
          {CONDITIONS.map((c) => <Button key={c} variant={c === condition ? "primary" : "secondary"} className="py-3 text-base" role="radio" aria-checked={c === condition} onClick={() => setCondition(c)}>{c}</Button>)}
        </div>
        <p className="mt-1 text-xs text-muted">{CONDITION_HELP[condition]}</p>
      </Field>}

      <div className="flex items-end gap-4">
        <Field label="Language"><Select aria-label="Language" value={language} onChange={setLanguage} options={LANGUAGES.map(([value, label]) => ({ value, label }))} /></Field>
        <Field label="Copies"><Stepper label="copies" value={isSlab && certTrim ? 1 : qty} min={1} max={isSlab && certTrim ? 1 : 99} onChange={setQty} /></Field>
      </div>

      {sameSlab && <p className="rounded bg-ok/15 px-3 py-2 text-sm text-ok">You already own a slab with this cert number: adding it again changes nothing.</p>}
      {same && <p className="rounded bg-ok/15 px-3 py-2 text-sm text-ok">You already own {same.quantity} in this condition: {qty === 1 ? "this adds one more copy to that stack" : `this adds ${qty} copies to that stack`} ({same.quantity + qty} total).</p>}

      <details className="rounded-lg border border-line bg-surface p-3">
        <summary className="cursor-pointer text-sm font-medium">Cost and how you got it{hasAcq ? " (set)" : " (optional)"}</summary>
        <div className="pt-3"><AcquiredForm initial={acq} qty={qty} hideSubmit onChange={setAcq} /></div>
      </details>

      {error && <p role="alert" className="rounded bg-danger/15 px-3 py-2 text-sm text-danger">{error}</p>}
      <Button className="w-full py-3 text-base" disabled={busy || (isSlab && !slabOk)}
        onClick={() => {
          const q = isSlab && certTrim ? 1 : qty;
          const extra = hasAcq ? { acquired: acq as Acquired } : {};
          const choice = { condition, language, acquired: hasAcq ? acq : null };
          if (isSlab && slabGrade !== null) {
            const grading: SlabGrading = { company: grader, grade: slabGrade, cert_number: certTrim || null, ...(grader === "OTHER" ? { grader_name: graderName.trim() } : {}) };
            onAdd({ card_id: card.id, variant, language, grading, quantity: q, ...extra }, choice);
          } else onAdd({ card_id: card.id, variant, language, condition, quantity: q, ...extra }, choice);
        }}>
        {busy ? "Adding…" : isSlab ? "Add slab to collection" : `Add ${qty} to collection`}</Button>
    </div>);
}
