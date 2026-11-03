import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { money, safeUrl } from "../lib/api";
import { compareGrades, gradeLabel } from "../lib/grades";
import { sourceLabel } from "../lib/colors";
import { Button, Input, Section, Select, SourceDot, Table, THead, Td, Th, Tr } from "./ui";

const CAP = 10;    // rows shown first; "Show more" adds STEP
const STEP = 20;
const WINDOWS = [{ value: "30", label: "Last 30 days" }, { value: "90", label: "Last 90 days" }, { value: "180", label: "Last 180 days" }];
const uniq = (xs: string[]) => [...new Set(xs)].sort();

/** Sold stats (one table) and the individual sales, filterable. */
export default function SalesList({ sales, stats }: { sales: any[]; stats: any[] }) {
  const [grade, setGrade] = useState("");
  const [source, setSource] = useState("");
  const [days, setDays] = useState("");
  const [text, setText] = useState("");
  const [limit, setLimit] = useState(CAP);
  if (!sales.length && !stats.length) return null;
  const src = (s: any): string => s.source ?? s.created_by ?? "";
  const since = days ? new Date(Date.now() - Number(days) * 864e5).toISOString().slice(0, 10) : "";
  const q = text.trim().toLowerCase();
  const rows = sales.filter((s) => (!grade || s.grade_key === grade) && (!source || src(s) === source)
    && (!since || String(s.sold_at).slice(0, 10) >= since) && (!q || String(s.title ?? "").toLowerCase().includes(q)));
  const filtered = !!(grade || source || days || q);
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setLimit(CAP); };
  const sortedStats = [...stats].sort((a, b) => compareGrades(a.grade_key, b.grade_key) || String(a.source).localeCompare(b.source));
  return (
    <Section title={`Sold (${sales.length})`} collapsible id="card-sold">
      {stats.length > 0 && (
        <Table className="mb-4">
          <THead><Th>Grade</Th><Th>Source</Th><Th num>Sales</Th><Th num>Min</Th><Th num>Avg</Th><Th num>Max</Th></THead>
          <tbody>{sortedStats.map((s, i) => (
            <Tr key={i}><Td className="font-medium">{gradeLabel(s.grade_key)}</Td><Td><SourceDot source={s.source} /></Td><Td num>{s.count}</Td>
              <Td num>{money(s.min, s.currency)}</Td><Td num>{money(s.avg, s.currency)}</Td><Td num>{money(s.max, s.currency)}</Td></Tr>))}</tbody>
        </Table>)}
      {sales.length > 0 && <>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="w-44"><Select aria-label="Grade filter" value={grade} onChange={reset(setGrade)} allLabel="All grades" options={uniq(sales.map((s) => s.grade_key)).map((g) => ({ value: g, label: gradeLabel(g) }))} /></div>
          <div className="w-44"><Select aria-label="Source filter" value={source} onChange={reset(setSource)} allLabel="All sources" options={uniq(sales.map(src)).map((s) => ({ value: s, label: sourceLabel(s) }))} /></div>
          <div className="w-44"><Select aria-label="Period filter" value={days} onChange={reset(setDays)} allLabel="All time" options={WINDOWS} /></div>
          <div className="w-44"><Input aria-label="Search listings" placeholder="Search titles" value={text} onChange={(e) => reset(setText)(e.target.value)} /></div>
          {filtered && <Button variant="ghost" size="sm" onClick={() => { setGrade(""); setSource(""); setDays(""); setText(""); setLimit(CAP); }}>Clear</Button>}
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
        {rows.length === 0 && <p className="mt-2 text-sm text-muted">No sales match these filters.</p>}
        <div className="mt-2 flex gap-2">
          {rows.length > limit && <Button variant="ghost" size="sm" onClick={() => setLimit(limit + STEP)}>Show {Math.min(STEP, rows.length - limit)} more</Button>}
          {limit > CAP && rows.length > CAP && <Button variant="ghost" size="sm" onClick={() => setLimit(CAP)}>Show less</Button>}
        </div>
      </>}
    </Section>);
}
