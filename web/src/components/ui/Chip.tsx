import type { ButtonHTMLAttributes } from "react";
import { cx } from "./cx";

/** Toggle pill (filters, source choice). */
export function Chip({ active, className, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { active: boolean }) {
  return <button type="button" aria-pressed={active}
    className={cx("rounded-full border px-2.5 py-1 text-xs font-medium transition",
      active ? "border-accent bg-accent/15 text-accent" : "border-line text-muted hover:text-fg", className)} {...p} />;
}
