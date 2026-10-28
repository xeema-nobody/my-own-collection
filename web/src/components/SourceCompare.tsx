import { ago, money } from "../lib/api";
import { KIND_CLASS, SOURCE_COLOR } from "../lib/colors";

const MATCH_WHY: Record<string, string> = {
  bucket: "company-agnostic grade bucket", lower: "lower grade of the same company", raw_fallback: "raw price (no graded price)",
};

/** Age of the data behind one source price: our fetch day, plus the upstream date when it differs a lot. */
function age(s: any) {
  const day = (d?: string | null) => (d ? ago(d.length === 10 ? d + "T12:00:00Z" : d) : null);
  const fetched = day(s.observed_on), upstream = day(s.as_of);
  if (s.price_kind === "sold") return upstream ? `last sale ${upstream}` : fetched ? `fetched ${fetched}` : "age unknown";
  if (s.as_of) return `upstream ${s.as_of.slice(0, 10)} (${upstream})`;
  return fetched ? `fetched ${fetched}` : "age unknown";
}

/**
 * Every source's price for one copy side by side + the headline rule.
 * `row` = compare payload: sources, spread, headline_rule, source (winning source), value.
 * `matches` = /cards/{id}/match (matched print per scraped source), optional.
 */
export default function SourceCompare({ row, matches, compact = false }: { row: any; matches?: any; compact?: boolean }) {
  const entries = Object.entries(row.sources ?? {}) as [string, any][];
  if (!entries.length) return <p className="text-sm opacity-70">No source has a price for this.</p>;
  const out = new Set<string>(row.spread?.outliers ?? []);
  const pct = row.spread?.pct ?? {};
  const winners = new Set<string>(String(row.source ?? "").split("+"));
  return (
    <div className="text-sm">
      {row.headline_rule && <p className="mb-1 text-xs opacity-80">Headline {money(row.value)}: {row.headline_rule}</p>}
      <table className="w-full"><thead><tr className="text-left text-xs opacity-60">
        <th>Source</th><th>Price</th><th>Kind</th>{!compact && <th>Match</th>}<th>Data</th>{!compact && <th>Print</th>}<th>vs median</th></tr></thead><tbody>
        {entries.map(([src, s]) => {
          const prod = matches?.[src]?.product;
          return (
            <tr key={src} className={`border-t dark:border-slate-700 ${winners.has(src) ? "font-medium" : ""}`}>
              <td style={{ color: SOURCE_COLOR[src] }}>{src}{winners.has(src) && <span title="This source produced the headline value"> ★</span>}</td>
              <td className={s.stale ? "line-through opacity-60" : ""}>{money(s.value)}</td>
              <td><span className={`rounded px-1 text-xs ${KIND_CLASS[s.price_kind] ?? ""}`}>{s.price_kind}</span>
                {s.thin && <span className="ml-1 text-xs text-amber-600 dark:text-amber-400">thin{s.sample_size ? ` (${s.sample_size})` : ""}</span>}</td>
              {!compact && <td className="text-xs">{s.match === "exact" ? "exact" : <span className="text-amber-600 dark:text-amber-400" title={MATCH_WHY[s.match]}>≈ {s.match} {s.grade_key_used}</span>}</td>}
              <td className="text-xs">{age(s)}{s.stale && <span className="ml-1 rounded bg-red-100 px-1 text-red-800 dark:bg-red-900 dark:text-red-200" title="Upstream date older than the staleness limit: only used when nothing fresher exists">stale</span>}</td>
              {!compact && <td className="text-xs">{prod ? <span title={prod.slug}>{prod.version ?? prod.slug}</span> : <span className="opacity-40">{src === "cardmarket" || src === "tcgplayer" ? "catalog" : "—"}</span>}</td>}
              <td className="text-xs">{pct[src] != null ? <span className={out.has(src) ? "rounded bg-amber-100 px-1 text-amber-800 dark:bg-amber-900 dark:text-amber-200" : "opacity-70"}
                title={out.has(src) ? "Far from the other sources: check the matched print / listing" : ""}>{pct[src] > 0 ? "+" : ""}{pct[src]}%{out.has(src) ? " ⚠ far off" : ""}</span> : "—"}</td>
            </tr>);
        })}
      </tbody></table>
      {entries.length === 2 && row.spread?.min != null && <p className="mt-1 text-xs opacity-60">Two sources: gap shown, no outlier flag (needs 3).</p>}
    </div>
  );
}
