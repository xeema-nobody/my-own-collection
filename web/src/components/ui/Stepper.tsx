import { Minus, Plus } from "lucide-react";
import { cx } from "./cx";

/** − value + control for small integers (quantities). */
export function Stepper({ value, onChange, min = 0, max, label, disabledInc, disabled, className }: {
  value: number; onChange: (v: number) => void; min?: number; max?: number; label: string;
  disabledInc?: boolean; disabled?: boolean; className?: string;
}) {
  const btn = "grid h-7 w-7 place-items-center rounded text-muted transition hover:bg-surface-2 hover:text-fg disabled:pointer-events-none disabled:opacity-40";
  return (
    <div role="group" aria-label={label} className={cx("inline-flex items-center rounded border border-line bg-surface", className)}>
      <button type="button" className={btn} aria-label={`Decrease ${label}`} disabled={disabled || value <= min} onClick={() => onChange(value - 1)}><Minus size={14} /></button>
      <span className="num w-8 text-center text-sm" aria-live="polite">{value}</span>
      <button type="button" className={btn} aria-label={`Increase ${label}`} disabled={disabled || disabledInc || (max != null && value >= max)} onClick={() => onChange(value + 1)}><Plus size={14} /></button>
    </div>);
}
