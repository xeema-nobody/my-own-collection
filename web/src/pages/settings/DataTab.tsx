import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api } from "../../lib/api";
import { errorText } from "../../components/QueryState";
import { Button, FileDrop, SegmentedControl, Section } from "../../components/ui";

const MODE_HINT = { set: "Sets each stack's quantity to the file value. Re-importing the same file changes nothing.", add: "Adds the file quantity to what you already own." };

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
        <p className="mb-3 text-sm text-muted">Download every stack with quantity, condition, grading and cost. Prices are not included.</p>
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
    </div>);
}
