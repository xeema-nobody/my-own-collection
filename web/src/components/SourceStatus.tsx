import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ago, api, SCRAPED_SOURCES, safeUrl } from "../lib/api";
import { refreshCardPrices } from "./CardFetch";
import { Badge, Button, SourceDot } from "./ui";

const TONE: Record<string, "ok" | "warn" | "neutral" | "danger"> = { ok: "ok", needs_match: "warn", not_found: "neutral" };

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
    <div className="space-y-2 text-sm">
      {SCRAPED_SOURCES.map((s) => {
        const l = log.data[s], m = match.data?.[s];
        return (
          <div key={s}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="w-36 font-medium"><SourceDot source={s} /></span>
              {l ? <Badge tone={TONE[l.status] ?? "danger"}>{l.status}</Badge> : <span className="text-muted">not fetched</span>}
              {l && <span className="text-muted">{ago(l.fetched_at)}{l.detail ? ` · ${l.detail}` : ""}</span>}
              {safeUrl(l?.url) && <a className="underline" href={safeUrl(l?.url)} target="_blank" rel="noreferrer">open</a>}
              {m?.url && <span className="text-xs" title="Matched product: different versions / prints of the same card have different prices">
                matched print: <b>{m.product?.version ?? "—"}</b> <span className="font-mono text-muted">{m.product?.slug}</span></span>}
              {m?.url && m.confirmed_by && <Button size="sm" variant="ghost" disabled={reset.isPending} onClick={() => reset.mutate(s)}>Reset match ({m.confirmed_by})</Button>}
            </div>
            {m?.candidates?.length > 0 && !(m.url && m.confirmed_by === "user") && (
              <ul className="ml-4 mt-1 space-y-1">
                <li className="text-xs text-muted">Several versions / prints share this card number and their prices differ: check the product page before choosing.</li>
                {m.candidates.map((c: any) => (
                  <li key={c.url} className="flex flex-wrap items-center gap-2">
                    <a className="underline" href={safeUrl(c.url)} target="_blank" rel="noreferrer">{c.title}</a>
                    {c.set_name && <span className="text-muted">{c.set_name}</span>}
                    <span className="font-mono text-xs text-muted">{c.product?.version ? `${c.product.version} · ` : ""}{c.product?.slug}</span>
                    <Button size="sm" variant="secondary" disabled={use.isPending} onClick={() => use.mutate({ source: s, url: c.url })}>Use this</Button>
                  </li>))}
              </ul>)}
          </div>);
      })}
      {(use.error || reset.error) && <p className="text-danger">{String(use.error ?? reset.error)}</p>}
    </div>
  );
}
