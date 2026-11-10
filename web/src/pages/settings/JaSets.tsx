import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { errorText } from "../../components/QueryState";
import { Badge, Button, Input, Section, Table, THead, Td, Th, Tr } from "../../components/ui";

/** Japanese Pokémon (TCGdex /ja): pick sets, import them on demand. Catalog only, never the collection. */
export default function JaSets({ jobs }: { jobs: UseQueryResult<any[]> }) {
  const qc = useQueryClient();
  const [load, setLoad] = useState(false);
  const [filter, setFilter] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const sets = useQuery({ queryKey: ["ja-sets"], queryFn: api.jaSets, enabled: load, staleTime: 5 * 60_000 });
  const imp = useMutation({
    mutationFn: (ids: string[]) => api.importJaSets(ids),
    onSuccess: () => setPicked(new Set()),
    onSettled: () => { qc.invalidateQueries({ queryKey: ["jobs"] }); qc.invalidateQueries({ queryKey: ["ja-sets"] }); qc.invalidateQueries({ queryKey: ["filters"] }); },
  });
  const importing = !!jobs.data?.find((j: any) => j.type === "catalog_import" && j.status === "running");
  const shown = useMemo(() => (sets.data ?? []).filter((s) => `${s.name} ${s.id}`.toLowerCase().includes(filter.toLowerCase())), [sets.data, filter]);
  const toggle = (id: string) => setPicked((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const err = sets.error || imp.error;

  return (
    <Section title="Japanese sets" id="settings-ja">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" disabled={sets.isFetching} onClick={() => (load ? sets.refetch() : setLoad(true))}>{sets.isFetching ? "Loading…" : "Load Japanese sets"}</Button>
        <Button disabled={importing || !picked.size} onClick={() => imp.mutate([...picked])}>Import selected ({picked.size})</Button>
        <span className="text-xs text-muted">Catalog only: cards are never added to the collection. Pick sets, the import runs in the background (Jobs tab).</span>
      </div>
      {err && <p className="mt-3 text-sm text-danger">{errorText(err)}</p>}
      {sets.data && (<>
        <div className="mt-3 w-64"><Input aria-label="Filter Japanese sets" placeholder="Filter by name or code…" value={filter} onChange={(e) => setFilter(e.target.value)} /></div>
        <Table className="mt-3 max-h-96 overflow-y-auto">
          <THead><Th className="w-8" /><Th>Set</Th><Th num>Cards</Th><Th num>Stored</Th><Th>State</Th></THead>
          <tbody>{shown.map((s) => (
            <Tr key={s.id}>
              <Td><input type="checkbox" aria-label={`Select ${s.name}`} className="h-4 w-4 accent-[rgb(var(--accent))]" checked={picked.has(s.id)} onChange={() => toggle(s.id)} /></Td>
              <Td>{s.name} <span className="text-xs text-muted">{s.id}</span></Td>
              <Td num>{s.total ?? "—"}</Td><Td num>{s.imported}</Td>
              <Td>{s.imported === 0 ? <Badge tone="warn">not imported</Badge> : s.total && s.imported < s.total ? <Badge tone="danger">{s.total - s.imported} missing</Badge> : <Badge tone="ok">complete</Badge>}</Td>
            </Tr>))}</tbody>
        </Table>
      </>)}
    </Section>);
}
