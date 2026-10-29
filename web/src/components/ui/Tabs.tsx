import * as RT from "@radix-ui/react-tabs";
import type { ReactNode } from "react";
import { cx } from "./cx";

export const Tabs = RT.Root;
export function TabList({ children }: { children: ReactNode }) {
  return <RT.List className="mb-3 flex gap-1 border-b border-line">{children}</RT.List>;
}
export function Tab({ value, children }: { value: string; children: ReactNode }) {
  return <RT.Trigger value={value} className="-mb-px border-b-2 border-transparent px-3 py-1.5 text-sm text-muted data-[state=active]:border-accent data-[state=active]:text-fg">{children}</RT.Trigger>;
}
export const TabPanel = RT.Content;

/** Pill-style single choice (view modes, ranges). */
export function SegmentedControl<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[]; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded bg-surface-2 p-0.5">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} onClick={() => onChange(o.value)}
          className={cx("rounded px-2.5 py-1 text-xs font-medium transition", o.value === value ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg")}>{o.label}</button>))}
    </div>);
}
