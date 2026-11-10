import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type JaSuggest } from "../../lib/api";
import { friendlyScanError } from "../../lib/scan";
import { Badge, Button, Input } from "../ui";

/**
 * No match for a scan / slab: offer to import the likely Japanese set into the catalog (never the collection, nothing is
 * added). One confirm, progress while the job runs, then `onImported` so the page re-runs the match.
 * `importedSet` = a set already imported this session whose re-match still found nothing.
 */
export default function JaImportPrompt({ code, total, setName, importedSet, onImported }: {
  code?: string | null; total?: number | null; setName?: string | null; importedSet?: string | null; onImported: (set: string) => void;
}) {
  const [typed, setTyped] = useState("");
  const [q, setQ] = useState("");
  const [chosen, setChosen] = useState<JaSuggest | null>(null);
  const [running, setRunning] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const sug = useQuery({ queryKey: ["ja-suggest", code, total, setName, q], queryFn: () => api.jaSuggest({ code, total, set_name: setName, q }), retry: false });
  const sets = (sug.data?.sets ?? []).filter((s) => s.id !== importedSet);
  const start = useMutation({
    mutationFn: (id: string) => api.jaImport(id),
    onSuccess: () => { setRunning(true); setFailed(null); },
    onError: (e) => setFailed(friendlyScanError(e)),
  });
  const status = useQuery({ queryKey: ["ja-import-status"], queryFn: api.jaImportStatus, enabled: running, refetchInterval: running ? 1500 : false, retry: false });
  const st = status.data;
  useEffect(() => {
    if (!running || !st || st.set !== chosen?.id || st.state === "running" || st.state === "idle") return;
    setRunning(false);
    if (st.state === "error" || (st.state === "partial" && !st.done)) setFailed(`The import of ${chosen.id} did not finish. Try again.`);
    else onImported(chosen.id);
  }, [st, running, chosen, onImported]);

  if (running) {
    const n = st?.set === chosen?.id ? st?.done ?? 0 : 0, of = st?.expected;
    return <section aria-label="Japanese set import" role="status" className="space-y-1 rounded-lg border border-line bg-surface p-3 text-sm">
      <p className="font-medium">Importing {chosen?.id} {chosen?.name}…</p>
      <p className="text-muted">{n}{of ? ` / ${of}` : ""} cards (catalog only). The match runs again when it is done.</p>
    </section>;
  }
  return (
    <section aria-label="Japanese set import" className="space-y-2 rounded-lg border border-line bg-surface p-3 text-sm">
      <p className="font-medium">{importedSet ? `Set ${importedSet} is imported, but this card is not in it.` : "No match. A Japanese card, or a set not in the catalog?"}</p>
      <p className="text-xs text-muted">Import a Japanese set into the catalog (not your collection; nothing is added) and the match runs again.</p>
      {sug.isFetching && <p className="text-muted">Looking for the set…</p>}
      {!sug.isFetching && sets.length === 0 && <p className="text-muted">No likely set found{q ? " for that search" : ""}. Search by set code or name below.</p>}
      <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Likely sets">
        {sets.map((s) => <Button key={s.id} type="button" size="sm" role="radio" aria-checked={chosen?.id === s.id} variant={chosen?.id === s.id ? "primary" : "secondary"} onClick={() => setChosen(s)}>
          {s.id} {s.name}{s.imported ? " (imported)" : ""}</Button>)}
      </div>
      {chosen && <p className="text-xs text-muted"><Badge tone="neutral">{chosen.reason}</Badge> {chosen.id}: {chosen.total ?? "?"} cards</p>}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setQ(typed.trim()); setChosen(null); }}>
        <Input aria-label="Search Japanese sets" placeholder="Set code or name (S9, SV2a)" value={typed} onChange={(e) => setTyped(e.target.value)} />
        <Button type="submit" variant="secondary" disabled={typed.trim().length < 2}>Search</Button>
      </form>
      {failed && <p role="alert" className="text-danger">{failed}</p>}
      <Button type="button" className="w-full" disabled={!chosen || start.isPending} onClick={() => chosen && start.mutate(chosen.id)}>
        {chosen ? `Import ${chosen.id} (${chosen.total ?? "?"} cards, catalog only)` : "Pick a set to import"}
      </Button>
    </section>);
}
