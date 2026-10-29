import { useEffect, useState } from "react";
import * as RP from "@radix-ui/react-popover";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ChevronDown, Search } from "lucide-react";
import { cx } from "./cx";
import type { Option } from "./Select";

export type ComboPage = { options: Option[]; more: boolean };

/**
 * Searchable single-choice picker for lists too long for a Select.
 * `fetchPage(q, page)` is called (debounced) per query; "Show more" loads the next page.
 * `cacheKey` namespaces the react-query cache. `selectedLabel` is shown while closed.
 */
export function Combobox({ value, selectedLabel, onChange, fetchPage, cacheKey, placeholder = "Pick…", "aria-label": aria, className }: {
  value: string; selectedLabel?: string; onChange: (value: string, label: string) => void;
  fetchPage: (q: string, page: number) => Promise<ComboPage>; cacheKey: string;
  placeholder?: string; "aria-label"?: string; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => { const t = setTimeout(() => setQ(text.trim()), 250); return () => clearTimeout(t); }, [text]);
  const res = useInfiniteQuery({
    queryKey: ["combobox", cacheKey, q], enabled: open, initialPageParam: 1,
    queryFn: ({ pageParam }) => fetchPage(q, pageParam),
    getNextPageParam: (last, all) => (last.more ? all.length + 1 : undefined),
  });
  const seen = new Set<string>();
  const options = (res.data?.pages ?? []).flatMap((p) => p.options).filter((o) => !seen.has(o.value) && !!seen.add(o.value));
  return (
    <RP.Root open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setText(""); setQ(""); } }}>
      <RP.Trigger aria-label={aria} className={cx("flex w-full items-center justify-between gap-2 rounded border border-line bg-surface px-2.5 py-1.5 text-left text-sm", className)}>
        <span className={cx("truncate", !value && "text-muted")}>{value ? selectedLabel || value : placeholder}</span>
        <ChevronDown size={14} className="shrink-0 text-muted" />
      </RP.Trigger>
      <RP.Portal>
        <RP.Content sideOffset={4} align="start" className="z-50 w-[var(--radix-popover-trigger-width)] min-w-72 rounded-lg border border-line bg-surface p-2 shadow-lg">
          <div className="relative mb-2">
            <Search size={14} className="absolute top-2.5 left-2.5 text-muted" />
            <input autoFocus aria-label="Search" placeholder="Search…" value={text} onChange={(e) => setText(e.target.value)}
              className="w-full rounded border border-line bg-bg py-1.5 pr-2 pl-8 text-sm placeholder:text-muted" />
          </div>
          <ul role="listbox" aria-label={aria} className="max-h-64 overflow-y-auto">
            {options.map((o) => (
              <li key={o.value} role="option" aria-selected={o.value === value}>
                <button type="button" onClick={() => { onChange(o.value, o.label); setOpen(false); }}
                  className={cx("w-full rounded px-2 py-1.5 text-left text-sm hover:bg-surface-2", o.value === value && "text-accent")}>{o.label}</button>
              </li>))}
          </ul>
          {res.isLoading && <p className="px-2 py-1.5 text-sm text-muted">Loading…</p>}
          {res.isError && <p role="alert" className="px-2 py-1.5 text-sm text-danger">{(res.error as Error).message}</p>}
          {res.isSuccess && options.length === 0 && <p className="px-2 py-1.5 text-sm text-muted">No matches</p>}
          {res.hasNextPage && (
            <button type="button" disabled={res.isFetchingNextPage} onClick={() => res.fetchNextPage()}
              className="mt-1 w-full rounded px-2 py-1.5 text-center text-xs text-accent hover:bg-surface-2">Show more</button>)}
        </RP.Content>
      </RP.Portal>
    </RP.Root>);
}
