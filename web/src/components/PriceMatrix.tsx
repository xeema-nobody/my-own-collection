import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ago, api, money, safeUrl } from "../lib/api";
import { gradeLabel, gradesOf } from "../lib/grades";
import { kindTone, sourceLabel } from "../lib/colors";
import type { PriceGrade } from "../lib/priceGrade";
import GradeSelector from "./GradeSelector";
import { Badge, Checkbox, SourceDot, Table, THead, Td, Th, Tr, cx } from "./ui";

export default function PriceMatrix({ pg }: { pg: PriceGrade }) {
  const [showAll, setShowAll] = useState(false);
  const sources = useQuery({ queryKey: ["price-sources"], queryFn: api.priceSources });
  const m = pg.matrix.data;
  if (!m || !sources.data) return <p className="text-sm text-muted">{pg.matrix.error ? String(pg.matrix.error) : "Loading prices…"}</p>;
  const keys = pg.company === "Raw" ? ["raw"] : gradesOf(pg.keys, pg.company);
  const has = (g: string, s: string) => !!m.cells[g]?.[s];
  const rows = showAll ? keys : keys.filter((g: string) => (m.sources as string[]).some((s) => has(g, s)));
  // Columns = sources with a price in the shown rows; registered-but-off sources only appear when "show all" is on.
  const cols: string[] = [...new Set<string>([...sources.data.map((s: any) => s.id), ...m.sources])]
    .filter((s) => (showAll ? sources.data.find((r: any) => r.id === s)?.enabled !== false || rows.some((g) => has(g, s)) : rows.some((g) => has(g, s))));
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <GradeSelector pg={pg} />
        {pg.company !== "Raw" && <Checkbox label="Show empty grades" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />}
      </div>
      {pg.company === "Any" && <p className="text-xs text-muted">Any grader has no grade 10: PriceCharting only publishes company-agnostic grades up to 9.5. Pick a company for 10s.</p>}
      {rows.length === 0 ? <p className="text-sm text-muted">No {pg.company} prices yet. Fetch prices to fill this in.</p> : (
        <Table>
          <THead><Th>Grade</Th>{cols.map((c) => <Th key={c}><SourceDot source={c} /></Th>)}</THead>
          <tbody>
            {rows.map((g: string) => (
              <Tr key={g} aria-selected={g === pg.grade} className={cx(g === pg.grade && "bg-accent/10", "cursor-pointer")} onClick={() => pg.setGrade(g)}>
                <Td className="font-medium whitespace-nowrap">{gradeLabel(g)}</Td>
                {cols.map((c) => {
                  const cell = m.cells[g]?.[c];
                  if (!cell) return <Td key={c} className="text-muted/50">—</Td>;
                  const tip = [cell.variant && `variant ${cell.variant}`, `observed ${cell.observed_on}`, cell.fetched_at && `fetched ${ago(cell.fetched_at)}`,
                    cell.as_of && `upstream ${String(cell.as_of).slice(0, 10)}`, cell.sample_size != null && `${cell.sample_size} sales`].filter(Boolean).join(" · ");
                  const price = money(cell.price, cell.currency);
                  return (
                    <Td key={c} title={`${sourceLabel(c)}: ${tip}`} className="whitespace-nowrap">
                      {safeUrl(cell.url) ? <a className="num underline decoration-dotted" href={safeUrl(cell.url)} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{price}</a> : <span className="num">{price}</span>}{" "}
                      <Badge tone={kindTone(cell.kind)}>{cell.kind}</Badge></Td>);
                })}
              </Tr>))}
          </tbody>
        </Table>)}
    </div>);
}
