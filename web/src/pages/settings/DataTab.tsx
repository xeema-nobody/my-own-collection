import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api, money } from "../../lib/api";
import { exitLabel } from "../../components/collection/RemoveStack";
import { errorText } from "../../components/QueryState";
import { Button, FileDrop, SegmentedControl, Section } from "../../components/ui";

const MODE_HINT = { set: "Sets each stack's quantity to the file value. Re-importing the same file changes nothing.", add: "Adds the file quantity to what you already own." };

function PhotosSection() {
  const q = useQuery({ queryKey: ["photos", "stats"], queryFn: api.photoStats });
  if (!q.data) return null;
  return (
    <Section title="Photos">
      <p className="text-sm"><span className="num font-semibold">{q.data.count}</span> photo{q.data.count === 1 ? "" : "s"} · <span className="num font-semibold">{(q.data.bytes / 1e6).toFixed(1)} MB</span> in the database.
        <span className="text-muted"> Each daily backup holds a full copy; <code>scripts/backup.sh --no-photos</code> leaves them out.</span></p>
    </Section>);
}

function SalesSection() {
  const q = useQuery({ queryKey: ["sales", "report"], queryFn: api.salesReport });
  const r = q.data;
  if (!r) return null;
  const n = (s: string) => r.by_status[s]?.stacks ?? 0;
  const sold = r.sold;
  return (
    <Section title="Sales">
      <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
        <div>Ready <span className="num font-semibold">{n("ready")}</span></div>
        <div>Listed <span className="num font-semibold">{n("listed")}</span> <span className="num text-muted">{money(r.listed_value)}</span></div>
        <div>Reserved / withdrawn <span className="num font-semibold">{n("reserved") + n("withdrawn")}</span></div>
        <div>Sold <span className="num font-semibold">{sold.sales}</span> <span className="num text-muted">{money(sold.revenue)}</span></div>
        <div>Fees + shipping <span className="num font-semibold">{money(sold.fees + sold.shipping)}</span></div>
        <div>Realised profit <span className="num font-semibold">{sold.realised == null ? "—" : money(sold.realised)}</span>
          {sold.realised != null && sold.realised_known < sold.sales && <span className="text-muted"> ({sold.realised_known}/{sold.sales} with cost)</span>}</div>
        <div>Avg days to sell <span className="num font-semibold">{sold.avg_days_to_sell ?? "—"}</span></div>
      </div>
      {Object.keys(r.platforms).length > 0 && <ul className="mt-2 text-sm text-muted">
        {Object.entries(r.platforms).map(([p, v]) => <li key={p} className="num">{p}: {v.stacks} stack{v.stacks === 1 ? "" : "s"} · {money(v.value)}</li>)}</ul>}
    </Section>);
}

function ExitsSection() {
  const q = useQuery({ queryKey: ["exits"], queryFn: api.collectionExits });
  const rows = q.data ?? [];
  return (
    <Section title="Sold, gifted and removed">
      {rows.length === 0 ? <p className="text-sm text-muted">Nothing yet. Use "Sell / remove" in a stack's details.</p> : (
        <ul className="divide-y divide-line text-sm">
          {rows.slice(0, 30).map((x) => (
            <li key={x.id} className="flex items-baseline justify-between gap-3 py-1.5">
              <span>{x.card?.name ?? x.card_id} <span className="text-muted">{x.card?.set} · ×{x.quantity}{x.note ? ` · ${x.note}` : ""}</span></span>
              <span className="num shrink-0 text-muted">{exitLabel(x.reason)}{x.price != null ? ` ${money(x.price, x.currency)}/ea` : ""}{x.platform ? ` · ${x.platform}` : ""}{x.realised != null ? ` · realised ${money(x.realised, x.currency)}` : ""} · {x.date}</span>
            </li>))}
        </ul>)}
    </Section>);
}

export default function DataTab() {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"set" | "add">("set");
  const xfer = useMutation({
    mutationFn: () => api.importCollection(file!, file!.name.toLowerCase().endsWith(".csv") ? "csv" : "json", mode),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["collection"] }),
  });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="Export collection">
        <p className="mb-3 text-sm text-muted">Download every stack with quantity, condition, grading, cost and how it was acquired. Prices are not included.</p>
        <div className="flex gap-2">
          <a className="inline-flex items-center gap-1.5 rounded border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-2" href={api.exportCollectionUrl("json")}><Download size={14} aria-hidden />Export JSON</a>
          <a className="inline-flex items-center gap-1.5 rounded border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-surface-2" href={api.exportCollectionUrl("csv")}><Download size={14} aria-hidden />Export CSV</a>
        </div>
        <p className="mt-3 text-xs text-muted">Full database backups: <code>scripts/backup.sh</code> (see docs/backup.md).</p>
      </Section>
      <Section title="Import collection">
        <FileDrop file={file} accept=".json,.csv" hint="Drop a .json or .csv file here, or click to choose" onFile={(f) => { setFile(f); xfer.reset(); }} />
        <div className="mt-3">
          <SegmentedControl label="Import mode" value={mode} onChange={setMode} options={[{ value: "set", label: "Set quantities" }, { value: "add", label: "Add to quantities" }]} />
          <p className="mt-1 text-xs text-muted">{MODE_HINT[mode]}</p>
        </div>
        <Button className="mt-3" disabled={!file || xfer.isPending} onClick={() => xfer.mutate()}>Import</Button>
        {xfer.data && (
          <div className="mt-3 rounded-lg bg-surface-2 p-3 text-sm">
            <p>Created {xfer.data.created}, updated {xfer.data.updated}, {xfer.data.errors.length} rejected.</p>
            {xfer.data.errors.length > 0 && <ul className="mt-1 text-xs text-danger">{xfer.data.errors.slice(0, 10).map((e) => <li key={e.row}>row {e.row}: {e.error}</li>)}</ul>}
          </div>)}
        {xfer.error && <p className="mt-3 text-sm text-danger">{errorText(xfer.error)}</p>}
      </Section>
      <div className="lg:col-span-2"><PhotosSection /></div>
      <div className="lg:col-span-2"><SalesSection /></div>
      <div className="lg:col-span-2"><ExitsSection /></div>
    </div>);
}
