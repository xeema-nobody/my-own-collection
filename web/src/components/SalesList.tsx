import { money } from "../lib/api";

export default function SalesList({ sales }: { sales: any[] }) {
  if (!sales.length) return null;
  return (
    <details className="mt-3 text-sm"><summary className="cursor-pointer font-medium">Sold listings ({sales.length})</summary>
      <table className="mt-1 w-full"><thead><tr className="text-left opacity-70"><th>Date</th><th>Source</th><th>Grade</th><th>Price</th><th>Title</th></tr></thead><tbody>
        {sales.map((s) => (
          <tr key={s.id} className="border-t dark:border-slate-700">
            <td>{String(s.sold_at).slice(0, 10)}</td><td>{s.source ?? s.created_by}</td><td>{s.grade_key}</td>
            <td>{money(s.price, s.currency)}</td><td className="truncate" title={s.title}>{s.title}</td></tr>))}
      </tbody></table></details>
  );
}
