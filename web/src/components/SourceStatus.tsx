import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ago, api, SCRAPED_SOURCES, safeUrl } from "../lib/api";
import { SOURCE_COLOR } from "../lib/colors";
import { refreshCardPrices } from "./CardFetch";

const BADGE: Record<string, string> = {
  ok: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200",
  needs_match: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  not_found: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
};

/** Last fetch outcome per scraped source + product match picker. */
export default function SourceStatus({ cardId }: { cardId: string }) {
  const qc = useQueryClient();
  const log = useQuery({ queryKey: ["fetch-status", cardId], queryFn: () => api.fetchStatus(cardId) });
  const match = useQuery({ queryKey: ["match", cardId], queryFn: () => api.cardMatches(cardId) });
  const use = useMutation({
    mutationFn: async (a: { source: string; url: string }) => {
      await api.confirmMatch(cardId, a.source, a.url);
      await api.fetchCardPrices(cardId, { sources: [a.source], force: true });
    },
    onSettled: () => { refreshCardPrices(qc, cardId); qc.invalidateQueries({ queryKey: ["jobs"] }); },
  });
  const reset = useMutation({
    mutationFn: (source: string) => api.clearMatch(cardId, source),
    onSettled: () => refreshCardPrices(qc, cardId),
  });
  if (!log.data) return null;
  return (
    <div className="mb-3 space-y-2 text-sm">
      {SCRAPED_SOURCES.map((s) => {
        const l = log.data[s], m = match.data?.[s];
        return (
          <div key={s}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="w-32 font-medium" style={{ color: SOURCE_COLOR[s] }}>{s}</span>
              {l ? <span className={`rounded px-1 text-xs ${BADGE[l.status] ?? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"}`}>{l.status}</span>
                : <span className="opacity-50">not fetched</span>}
              {l && <span className="opacity-70">{ago(l.fetched_at)}{l.detail ? ` · ${l.detail}` : ""}</span>}
              {safeUrl(l?.url) && <a className="underline" href={safeUrl(l?.url)} target="_blank" rel="noreferrer">open</a>}
              {m?.url && <span className="text-xs" title="Matched product: different versions / prints of the same card have different prices">
                matched print: <b>{m.product?.version ?? "—"}</b> <span className="font-mono opacity-60">{m.product?.slug}</span></span>}
              {m?.url && m.confirmed_by && <button className="btn-ghost" disabled={reset.isPending} onClick={() => reset.mutate(s)}>Reset match ({m.confirmed_by})</button>}
            </div>
            {m?.candidates?.length > 0 && !(m.url && m.confirmed_by === "user") && (
              <ul className="ml-4 mt-1 space-y-1">
                <li className="text-xs opacity-70">Several versions / prints share this card number and their prices differ: check the product page before choosing.</li>
                {m.candidates.map((c: any) => (
                  <li key={c.url} className="flex items-center gap-2">
                    <a className="underline" href={safeUrl(c.url)} target="_blank" rel="noreferrer">{c.title}</a>
                    {c.set_name && <span className="opacity-60">{c.set_name}</span>}
                    <span className="font-mono text-xs opacity-60">{c.product?.version ? `${c.product.version} · ` : ""}{c.product?.slug}</span>
                    <button className="btn-ghost" disabled={use.isPending} onClick={() => use.mutate({ source: s, url: c.url })}>Use this</button>
                  </li>))}
              </ul>)}
          </div>);
      })}
      {(use.error || reset.error) && <p className="text-red-500">{String(use.error ?? reset.error)}</p>}
    </div>
  );
}
