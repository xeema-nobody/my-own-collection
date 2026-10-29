import type { ReactNode } from "react";
import { cx } from "./cx";

/** Big number with a label and optional hint. */
export function Kpi({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "ok" | "danger" }) {
  return (
    <div className="rounded-lg bg-surface p-4 shadow-card">
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className={cx("num mt-1 text-2xl font-semibold", tone === "ok" && "text-ok", tone === "danger" && "text-danger")}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </div>);
}
