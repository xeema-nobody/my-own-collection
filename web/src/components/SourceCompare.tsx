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

export type Copy = { label?: string; row: any };

/**
 * Every source's price for one or more copies side by side, in ONE table: a group row per copy
 * (label + headline rule), then one row per source. Columns and legend appear once.
 * `row` = compare payload: sources, spread, headline_rule, source (winning source), value.
 * `matches` = /cards/{id}/match (matched print per scraped source), optional.
 */
export function CompareCopies({ copies, matches, compact = false }: { copies: Copy[]; matches?: any; compact?: boolean }) {
  const shown = copies.filter((c) => Object.keys(c.row.sources ?? {}).length);
  if (!shown.length) return <p className="text-sm text-muted">No source has a price for this.</p>;
  const cols = compact ? 5 : 7;
  return (
    <div className="text-sm">
      <Table>
        <THead><Th>Source</Th><Th num>Price</Th><Th>Kind</Th>{!compact && <Th>Match</Th>}<Th>Data</Th>{!compact && <Th>Print</Th>}<Th num>vs median</Th></THead>
        <tbody>
        {shown.map(({ label, row }, n) => {
          const entries = Object.entries(row.sources) as [string, any][];
          const out = new Set<string>(row.spread?.outliers ?? []);
          const pct = row.spread?.pct ?? {};
          const winners = new Set<string>(String(row.source ?? "").split("+"));
          return [
            (label || row.headline_rule) && (
              <Tr key={`h${n}`} className="bg-surface-2/60">
                <Td colSpan={cols} className="py-1.5 text-xs text-muted">
                  {label && <b className="mr-2 text-fg">{label}</b>}{row.headline_rule && <>Headline {money(row.value)}: {row.headline_rule}</>}
                  {entries.length === 2 && row.spread?.min != null && <> · two sources: gap shown, no outlier flag (needs 3)</>}
                </Td>
              </Tr>),
            ...entries.map(([src, s]) => {
              const prod = matches?.[src]?.product;
              return (
                <Tr key={`${n}-${src}`} className={winners.has(src) ? "font-medium" : ""}>
                  <Td className="whitespace-nowrap"><SourceDot source={src} />{winners.has(src) && <span title="This source produced the headline value" className="text-accent"> ★</span>}</Td>
                  <Td num className={s.stale ? "line-through text-muted" : ""}>{money(s.value)}</Td>
                  <Td><Badge tone={kindTone(s.price_kind)}>{s.price_kind}</Badge>
                    {s.thin && <Badge tone="warn" className="ml-1">thin{s.sample_size ? ` (${s.sample_size})` : ""}</Badge>}</Td>
                  {!compact && <Td className="text-xs">{s.match === "exact" ? "exact" : <span className="text-warn" title={MATCH_WHY[s.match]}>≈ {s.match} {s.grade_key_used}</span>}</Td>}
                  <Td className="text-xs">{age(s)}{s.stale && <Badge tone="danger" className="ml-1" title="Upstream date older than the staleness limit: only used when nothing fresher exists">stale</Badge>}</Td>
                  {!compact && <Td className="text-xs">{prod ? <span title={prod.slug}>{prod.title ?? prod.version ?? prod.slug}</span> : <span className="text-muted">{src === "cardmarket" || src === "tcgplayer" ? "catalog" : src === "altxyz" ? "search" : "—"}</span>}</Td>}
                  <Td num className="text-xs">{pct[src] != null ? <span className={out.has(src) ? "rounded bg-warn/15 px-1 text-warn" : "text-muted"}
                    title={out.has(src) ? "Far from the other sources: check the matched print / listing" : ""}>{pct[src] > 0 ? "+" : ""}{pct[src]}%{out.has(src) ? " ⚠ far off" : ""}</span> : "—"}</Td>
                </Tr>);
            })];
        })}
        </tbody>
      </Table>
    </div>
  );
}

/** One copy (collection page stack). */
export default function SourceCompare({ row, matches, compact = false }: { row: any; matches?: any; compact?: boolean }) {
  return <CompareCopies copies={[{ row }]} matches={matches} compact={compact} />;
}
