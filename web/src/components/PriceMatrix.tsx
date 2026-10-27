import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, money } from "../lib/api";
import { KIND_CLASS, SOURCE_COLOR } from "../lib/colors";

const GRADERS = ["PSA", "BGS", "CGC"];

export default function PriceMatrix({ cardId }: { cardId: string }) {
  const [grader, setGrader] = useState("PSA");
  const matrix = useQuery({ queryKey: ["matrix", cardId], queryFn: () => api.priceMatrix(cardId) });
  const sources = useQuery({ queryKey: ["price-sources"], queryFn: api.priceSources });
  if (!matrix.data || !sources.data) return <p className="text-sm opacity-70">{matrix.error ? String(matrix.error) : "Loading prices…"}</p>;
  const m = matrix.data;
  // Columns = registered sources (pokemontcg.io stores under tcgplayer/cardmarket) + any stored source not registered.
  const cols: { id: string; label: string; enabled: boolean }[] = [
    ...sources.data.filter((s: any) => s.id !== "pokemontcg").map((s: any) => ({ id: s.id, label: s.id, enabled: s.enabled })),
    ...m.sources.filter((s: string) => !sources.data.some((r: any) => r.id === s)).map((s: string) => ({ id: s, label: s, enabled: true })),
  ];
  const rows: string[] = ["raw", ...m.grades.filter((g: string) => g.startsWith(grader))];
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-sm">
        <span className="opacity-70">Grader</span>
        <select className="input" value={grader} onChange={(e) => setGrader(e.target.value)}>{GRADERS.map((g) => <option key={g}>{g}</option>)}</select>
      </div>
      <table className="w-full text-sm"><thead><tr className="text-left opacity-70"><th>Grade</th>
        {cols.map((c) => <th key={c.id} style={{ color: SOURCE_COLOR[c.id] }} title={c.enabled ? "" : "not fetching yet"}>{c.label}{!c.enabled && <span className="opacity-50"> ·off</span>}</th>)}
      </tr></thead><tbody>
        {rows.map((g) => (
          <tr key={g} className="border-t dark:border-slate-700">
            <td className="py-1 font-medium">{g === "raw" ? "Raw" : g.replace(grader, grader + " ")}</td>
            {cols.map((c) => {
              const cell = m.cells[g]?.[c.id];
              if (!cell) return <td key={c.id} className="opacity-40">—</td>;
              const tip = [cell.variant && `variant ${cell.variant}`, `observed ${cell.observed_on}`,
                cell.as_of && `upstream ${String(cell.as_of).slice(0, 10)}`, cell.sample_size != null && `${cell.sample_size} sales`].filter(Boolean).join(" · ");
              return (
                <td key={c.id} title={tip}>{money(cell.price, cell.currency)}{" "}
                  <span className={`rounded px-1 text-xs ${KIND_CLASS[cell.kind] ?? ""}`}>{cell.kind}</span></td>);
            })}
          </tr>))}
      </tbody></table>
    </div>
  );
}
