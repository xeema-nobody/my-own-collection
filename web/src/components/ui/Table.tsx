import type { ReactNode, ThHTMLAttributes, TdHTMLAttributes, HTMLAttributes } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { cx } from "./cx";

/** Scrolling table frame; the head sticks to the top of the scroll area. */
export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("overflow-x-auto rounded-lg bg-surface shadow-card", className)}><table className="w-full text-sm">{children}</table></div>;
}
export function THead({ children }: { children: ReactNode }) {
  return <thead className="sticky top-0 z-10 bg-surface text-left text-xs text-muted"><tr className="border-b border-line">{children}</tr></thead>;
}
export function Th({ num, className, ...p }: ThHTMLAttributes<HTMLTableCellElement> & { num?: boolean }) {
  return <th scope="col" className={cx("px-3 py-2 font-medium whitespace-nowrap", num && "text-right", className)} {...p} />;
}
export function Tr({ className, ...p }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cx("border-b border-line/60 last:border-0", className)} {...p} />;
}
export function Td({ num, className, ...p }: TdHTMLAttributes<HTMLTableCellElement> & { num?: boolean }) {
  return <td className={cx("px-3 py-2 align-middle", num && "num text-right", className)} {...p} />;
}

/** Header cell that toggles sorting. `dir` is set only on the active column. */
export function SortTh({ label, active, dir, onSort, num }: { label: string; active: boolean; dir: "asc" | "desc"; onSort: () => void; num?: boolean }) {
  const Icon = dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <Th num={num} aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={onSort} className={cx("inline-flex items-center gap-1 rounded hover:text-fg", active && "text-fg")}>
        {label}{active && <Icon size={12} aria-hidden />}
      </button>
    </Th>);
}
