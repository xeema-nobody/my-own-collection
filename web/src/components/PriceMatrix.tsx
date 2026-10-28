import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ago, api, money } from "../lib/api";
import { KIND_CLASS, SOURCE_COLOR } from "../lib/colors";

const BUCKET = /^G(\d+(?:\.\d+)?)$/;
const label = (g: string) => g === "raw" ? "Raw" : BUCKET.test(g) ? g.replace("G", "Grade ") + " (any grader)" : g.replace(/^([A-Za-z]+?)(\d)/, "$1 $2");

export default function PriceMatrix({ cardId }: { cardId: string }) {
  const [grader, setGrader] = useState("PSA");
  const matrix = useQuery({ queryKey: ["matrix", cardId], queryFn: () => api.priceMatrix(cardId) });
  const sources = useQuery({ queryKey: ["price-sources"], queryFn: api.priceSources });
  if (!matrix.data || !sources.data) return <p className="text-sm opacity-70">{matrix.error ? String(matrix.error) : "Loading prices…"}</p>;
  const m = matrix.data;
  // Columns = registered sources (ids = stored ids) + any stored source not registered.
  const cols: { id: string; label: string; enabled: boolean }[] = [
    ...sources.data.map((s: any) => ({ id: s.id, label: s.id, enabled: s.enabled })),
    ...m.sources.filter((s: string) => !sources.data.some((r: any) => r.id === s)).map((s: string) => ({ id: s, label: s, enabled: true })),
  ];
  const graders: string[] = m.graders;
  const sel = graders.includes(grader) ? grader : graders[0];
  const rows: string[] = m.grades.filter((g: string) => g === "raw" || BUCKET.test(g) || (sel && g.toUpperCase().startsWith(sel)));
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-sm">
        <span className="opacity-70">Grader</span>
        <select className="input" value={sel} onChange={(e) => setGrader(e.target.value)}>{graders.map((g) => <option key={g}>{g}</option>)}</select>
      </div>
      <table className="w-full text-sm"><thead><tr className="text-left opacity-70"><th>Grade</th>
        {cols.map((c) => <th key={c.id} style={{ color: SOURCE_COLOR[c.id] }} title={c.enabled ? "" : "not fetching yet"}>{c.label}{!c.enabled && <span className="opacity-50"> ·off</span>}</th>)}
      </tr></thead><tbody>
        {rows.map((g) => (
          <tr key={g} className="border-t dark:border-slate-700">
            <td className="py-1 font-medium">{label(g)}</td>
            {cols.map((c) => {
              const cell = m.cells[g]?.[c.id];
              if (!cell) return <td key={c.id} className="opacity-40">—</td>;
              const tip = [cell.variant && `variant ${cell.variant}`, `observed ${cell.observed_on}`, cell.fetched_at && `fetched ${ago(cell.fetched_at)}`,
                cell.as_of && `upstream ${String(cell.as_of).slice(0, 10)}`, cell.sample_size != null && `${cell.sample_size} sales`].filter(Boolean).join(" · ");
              return (
                <td key={c.id} title={tip}>
                  {cell.url ? <a className="underline decoration-dotted" href={cell.url} target="_blank" rel="noreferrer">{money(cell.price, cell.currency)}</a> : money(cell.price, cell.currency)}{" "}
                  <span className={`rounded px-1 text-xs ${KIND_CLASS[cell.kind] ?? ""}`}>{cell.kind}</span></td>);
            })}
          </tr>))}
      </tbody></table>
    </div>
  );
}
