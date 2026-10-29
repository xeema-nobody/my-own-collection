import { cx } from "./cx";

export type BarRow = { name: string; value: number };

/** Top-N rows by value (largest first) with the rest folded into one "Other" row. */
export function topN(rows: BarRow[], n: number): BarRow[] {
  const sorted = [...rows].sort((a, b) => b.value - a.value);
  if (sorted.length <= n) return sorted;
  const rest = sorted.slice(n).reduce((a, r) => a + r.value, 0);
  return [...sorted.slice(0, n), { name: "Other", value: rest }];
}

/** Ranked horizontal bars: full-width label, value and share of total. Pure CSS, so long names wrap instead of being cut. */
export function BarList({ rows, format, max = 10, label }: { rows: BarRow[]; format: (v: number) => string; max?: number; label: string }) {
  const total = rows.reduce((a, r) => a + r.value, 0);
  const shown = topN(rows, max);
  const top = Math.max(1, ...shown.map((r) => r.value));
  return (
    <ul aria-label={label} className="space-y-2">
      {shown.map((r) => {
        const pct = total ? (r.value / total) * 100 : 0;
        return (
          <li key={r.name} className="text-sm">
            <div className="flex items-baseline justify-between gap-3">
              <span className={cx("min-w-0 break-words", r.name === "Other" && "text-muted")}>{r.name}</span>
              <span className="num shrink-0"><span className="font-medium">{format(r.value)}</span> <span className="text-muted">{pct.toFixed(pct < 10 ? 1 : 0)}%</span></span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-surface-2"><div role="presentation" className={cx("h-full rounded-full", r.name === "Other" ? "bg-muted" : "bg-accent")} style={{ width: `${(r.value / top) * 100}%` }} /></div>
          </li>);
      })}
    </ul>);
}
