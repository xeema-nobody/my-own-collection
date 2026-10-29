import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { money, safeUrl } from "../lib/api";
import { gradeLabel } from "../lib/grades";
import { sourceLabel } from "../lib/colors";
import { Button, Section, Select, SourceDot, Table, THead, Td, Th, Tr } from "./ui";

const STEP = 20;
const uniq = (xs: string[]) => [...new Set(xs)].sort();

/** Sold stats (one table) and the individual sales, filterable. */
export default function SalesList({ sales, stats }: { sales: any[]; stats: any[] }) {
  const [grade, setGrade] = useState("");
  const [source, setSource] = useState("");
  const [limit, setLimit] = useState(STEP);
  if (!sales.length && !stats.length) return null;
  const src = (s: any): string => s.source ?? s.created_by ?? "";
  const rows = sales.filter((s) => (!grade || s.grade_key === grade) && (!source || src(s) === source));
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setLimit(STEP); };
  return (
    <Section title={`Sold (${sales.length})`} collapsible id="card-sold">
      {stats.length > 0 && (
        <Table className="mb-4">
          <THead><Th>Grade</Th><Th>Source</Th><Th num>Sales</Th><Th num>Min</Th><Th num>Avg</Th><Th num>Max</Th></THead>
          <tbody>{stats.map((s, i) => (
            <Tr key={i}><Td className="font-medium">{gradeLabel(s.grade_key)}</Td><Td><SourceDot source={s.source} /></Td><Td num>{s.count}</Td>
              <Td num>{money(s.min, s.currency)}</Td><Td num>{money(s.avg, s.currency)}</Td><Td num>{money(s.max, s.currency)}</Td></Tr>))}</tbody>
        </Table>)}
      {sales.length > 0 && <>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="w-44"><Select aria-label="Grade filter" value={grade} onChange={reset(setGrade)} allLabel="All grades" options={uniq(sales.map((s) => s.grade_key)).map((g) => ({ value: g, label: gradeLabel(g) }))} /></div>
          <div className="w-44"><Select aria-label="Source filter" value={source} onChange={reset(setSource)} allLabel="All sources" options={uniq(sales.map(src)).map((s) => ({ value: s, label: sourceLabel(s) }))} /></div>
          <span className="ml-auto text-xs text-muted">{rows.length} of {sales.length}</span>
        </div>
        <Table>
          <THead><Th>Date</Th><Th>Source</Th><Th>Grade</Th><Th num>Price</Th><Th>Listing</Th></THead>
          <tbody>{rows.slice(0, limit).map((s) => {
            const url = safeUrl(s.url);
            return (
              <Tr key={s.id}>
                <Td className="whitespace-nowrap text-muted">{String(s.sold_at).slice(0, 10)}</Td>
                <Td className="whitespace-nowrap"><SourceDot source={src(s)} /></Td>
                <Td className="whitespace-nowrap">{gradeLabel(s.grade_key)}</Td>
                <Td num className="whitespace-nowrap">{money(s.price, s.currency)}</Td>
                <Td className="max-w-0 w-full"><span className="flex items-center gap-1.5"><span className="truncate" title={s.title}>{s.title}</span>
                  {url && <a href={url} target="_blank" rel="noreferrer" aria-label="Open listing" className="shrink-0 text-muted hover:text-fg"><ExternalLink size={13} /></a>}</span></Td>
              </Tr>);
          })}</tbody>
        </Table>
        {rows.length > limit && <Button variant="ghost" size="sm" className="mt-2" onClick={() => setLimit(limit + STEP)}>Show {Math.min(STEP, rows.length - limit)} more</Button>}
      </>}
    </Section>);
}
