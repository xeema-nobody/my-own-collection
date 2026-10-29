import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./Button";
import { Select } from "./Select";

export const PAGE_SIZES = [25, 50, 100, 200];

/** Prev/next with a "from-to of total" label and a page-size select. */
export function Pagination({ page, pageSize, total, onPage, onPageSize }: {
  page: number; pageSize: number; total: number; onPage: (p: number) => void; onPageSize: (n: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted">
      <span className="num">{from}-{to} of {total}</span>
      <div className="flex items-center gap-2">
        <div className="w-28"><Select aria-label="Rows per page" value={String(pageSize)} onChange={(v) => onPageSize(Number(v))}
          options={PAGE_SIZES.map((n) => ({ value: String(n), label: `${n} / page` }))} /></div>
        <Button variant="secondary" size="sm" aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft size={14} /></Button>
        <span className="num">{page} / {pages}</span>
        <Button variant="secondary" size="sm" aria-label="Next page" disabled={page >= pages} onClick={() => onPage(page + 1)}><ChevronRight size={14} /></Button>
      </div>
    </div>);
}
