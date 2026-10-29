import { useState } from "react";
import { useMutation, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { api, ApiError, FETCHER_START_CMD, SCRAPED_SOURCES } from "../../lib/api";
import { errorText } from "../../components/QueryState";
import FetcherBadge from "../../components/FetcherBadge";
import FetchProgress from "../../components/FetchProgress";
import { Badge, Button, Checkbox, Chip, Section, SegmentedControl, Table, THead, Td, Th, Tr } from "../../components/ui";

type Scope = "sets" | "owned" | "missing";
const SCOPE_HINT: Record<Scope, string> = {
  sets: "Every card of the sets selected on the Catalog tab.",
  owned: "Every card in your collection.",
  missing: "Owned cards whose graded stack has no graded price yet.",
};

export default function PricesTab({ status, jobs, picked }: { status: UseQueryResult<any>; jobs: UseQueryResult<any[]>; picked: Set<string> }) {
  const qc = useQueryClient();
  const [scope, setScope] = useState<Scope>("sets");
  const [sources, setSources] = useState<string[]>([...SCRAPED_SOURCES]);
  const [force, setForce] = useState(false);
  const ids = [...picked];
  const fetchAll = useMutation({
    mutationFn: () => api.fetchPrices({ ...(scope === "owned" ? { owned: true } : scope === "missing" ? { missing: true } : { sets: ids }), sources, force }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
  const fetching = !!jobs.data?.find((j: any) => j.type === "price_fetch" && j.status === "running");
  const lastFetch = jobs.data?.find((j: any) => j.type === "price_fetch");
  const e = fetchAll.error;
  const fetchErr = e instanceof ApiError && e.status === 503 ? `Fetcher not reachable. Start it on the host: ${FETCHER_START_CMD}`
    : e instanceof ApiError && e.status === 409 ? "A price fetch is already running." : e ? errorText(e) : null;
  const s = status.data;
  return (
    <div className="space-y-4">
      <Section title="Price fetching" actions={<FetcherBadge />}>
        <p className="mb-3 text-sm text-muted">Sold and graded prices from PriceCharting, Cardmarket and alt.xyz through the host fetcher (24 h cache). Runs on demand only.</p>
        <div className="space-y-3">
          <div>
            <SegmentedControl label="Scope" value={scope} onChange={setScope} options={[
              { value: "sets", label: `Selected sets (${ids.length})` }, { value: "owned", label: "Owned collection" }, { value: "missing", label: "Missing prices" }]} />
            <p className="mt-1 text-xs text-muted">{SCOPE_HINT[scope]}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Sources">
            <span className="text-xs text-muted">Sources</span>
            {SCRAPED_SOURCES.map((x) => <Chip key={x} active={sources.includes(x)} onClick={() => setSources((v) => v.includes(x) ? v.filter((y) => y !== x) : [...v, x])}>{x}</Chip>)}
          </div>
          <div>
            <Checkbox label="Force (ignore the 24 h cache)" checked={force} onChange={(ev) => setForce(ev.target.checked)} />
            <p className="ml-6 text-xs text-muted">Re-fetches cards fetched in the last 24 h. alt.xyz takes about a minute per card.</p>
          </div>
          <Button disabled={fetching || fetchAll.isPending || !sources.length || (scope === "sets" && !ids.length)} onClick={() => fetchAll.mutate()}>
            {fetching ? "Fetching…" : "Fetch prices"}</Button>
        </div>
        {fetchErr && <p className="mt-3 text-sm text-danger">{fetchErr}</p>}
        <FetchProgress job={lastFetch} live={fetching} />
      </Section>
      {s && <Section title="Price sources">
        <Table><THead><Th>Source</Th><Th>Kinds</Th><Th>Grades</Th><Th>Status</Th></THead><tbody>
          {s.price_sources.map((p: any) => <Tr key={p.id} title={p.note}><Td>{p.label}</Td><Td className="text-muted">{p.kinds.join(", ")}</Td><Td className="text-muted">{p.grades}</Td>
            <Td><Badge tone={p.enabled ? "ok" : "neutral"}>{p.enabled ? "enabled" : "not available yet"}</Badge></Td></Tr>)}
        </tbody></Table>
      </Section>}
    </div>);
}
