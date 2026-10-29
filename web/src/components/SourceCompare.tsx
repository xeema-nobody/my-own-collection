import { ago, money } from "../lib/api";
import { kindTone } from "../lib/colors";
import { Badge, SourceDot, Table, THead, Td, Th, Tr } from "./ui";

const MATCH_WHY: Record<string, string> = {
  bucket: "company-agnostic grade bucket", lower: "lower grade of the same company", needs_graded_price: "no graded price: not counted",
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
  if (!entries.length) return <p className="text-sm text-muted">No source has a price for this.</p>;
  const out = new Set<string>(row.spread?.outliers ?? []);
  const pct = row.spread?.pct ?? {};
  const winners = new Set<string>(String(row.source ?? "").split("+"));
  return (
    <div className="text-sm">
      {row.headline_rule && <p className="mb-1 text-xs text-muted">Headline {money(row.value)}: {row.headline_rule}</p>}
      <Table>
        <THead><Th>Source</Th><Th num>Price</Th><Th>Kind</Th>{!compact && <Th>Match</Th>}<Th>Data</Th>{!compact && <Th>Print</Th>}<Th num>vs median</Th></THead>
        <tbody>
        {entries.map(([src, s]) => {
          const prod = matches?.[src]?.product;
          return (
            <Tr key={src} className={winners.has(src) ? "font-medium" : ""}>
              <Td className="whitespace-nowrap"><SourceDot source={src} />{winners.has(src) && <span title="This source produced the headline value" className="text-accent"> ★</span>}</Td>
              <Td num className={s.stale ? "line-through text-muted" : ""}>{money(s.value)}</Td>
              <Td><Badge tone={kindTone(s.price_kind)}>{s.price_kind}</Badge>
                {s.thin && <Badge tone="warn" className="ml-1">thin{s.sample_size ? ` (${s.sample_size})` : ""}</Badge>}</Td>
              {!compact && <Td className="text-xs">{s.match === "exact" ? "exact" : <span className="text-warn" title={MATCH_WHY[s.match]}>≈ {s.match} {s.grade_key_used}</span>}</Td>}
              <Td className="text-xs">{age(s)}{s.stale && <Badge tone="danger" className="ml-1" title="Upstream date older than the staleness limit: only used when nothing fresher exists">stale</Badge>}</Td>
              {!compact && <Td className="text-xs">{prod ? <span title={prod.slug}>{prod.version ?? prod.slug}</span> : <span className="text-muted">{src === "cardmarket" || src === "tcgplayer" ? "catalog" : "—"}</span>}</Td>}
              <Td num className="text-xs">{pct[src] != null ? <span className={out.has(src) ? "rounded bg-warn/15 px-1 text-warn" : "text-muted"}
                title={out.has(src) ? "Far from the other sources: check the matched print / listing" : ""}>{pct[src] > 0 ? "+" : ""}{pct[src]}%{out.has(src) ? " ⚠ far off" : ""}</span> : "—"}</Td>
            </Tr>);
        })}
        </tbody>
      </Table>
      {entries.length === 2 && row.spread?.min != null && <p className="mt-1 text-xs text-muted">Two sources: gap shown, no outlier flag (needs 3).</p>}
    </div>
  );
}
