import * as RS from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cx } from "./cx";

export type Option = { value: string; label: string };
/** Radix forbids an empty item value, so the "no filter" option uses this sentinel. */
const NONE = "__none__";

/** Styled accessible select. `allLabel` adds a leading option that maps to value "". */
export function Select({ value, onChange, options, allLabel, placeholder, className, "aria-label": aria }: {
  value: string; onChange: (v: string) => void; options: Option[]; allLabel?: string; placeholder?: string; className?: string; "aria-label"?: string;
}) {
  return (
    <RS.Root value={value === "" && allLabel ? NONE : value} onValueChange={(v) => onChange(v === NONE ? "" : v)}>
      <RS.Trigger aria-label={aria} className={cx("flex w-full items-center justify-between gap-2 rounded border border-line bg-surface px-2.5 py-1.5 text-left text-sm", className)}>
        <RS.Value placeholder={placeholder} />
        <RS.Icon><ChevronDown size={14} className="text-muted" /></RS.Icon>
      </RS.Trigger>
      <RS.Portal>
        <RS.Content position="popper" sideOffset={4} className="z-50 max-h-72 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border border-line bg-surface shadow-lg">
          <RS.Viewport className="p-1">
            {allLabel && <Item value={NONE} label={allLabel} />}
            {options.map((o) => <Item key={o.value} value={o.value} label={o.label} />)}
          </RS.Viewport>
        </RS.Content>
      </RS.Portal>
    </RS.Root>);
}

function Item({ value, label }: Option) {
  return (
    <RS.Item value={value} className="flex cursor-pointer items-center justify-between gap-2 rounded px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-surface-2">
      <RS.ItemText>{label}</RS.ItemText>
      <RS.ItemIndicator><Check size={14} className="text-accent" /></RS.ItemIndicator>
    </RS.Item>);
}
