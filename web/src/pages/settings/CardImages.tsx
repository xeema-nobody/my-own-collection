import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { errorText } from "../../components/QueryState";
import { Badge, Button, Section } from "../../components/ui";

/** Card artwork hosts: move stored images from images.pokemontcg.io (deprecated API family) to TCGdex assets. */
export default function CardImages({ jobs }: { jobs: UseQueryResult<any[]> }) {
  const qc = useQueryClient();
  const running = !!jobs.data?.find((j: any) => j.type === "catalog_images" && j.status === "running");
  const st = useQuery({ queryKey: ["card-images"], queryFn: api.catalogImagesStatus, refetchInterval: () => (running ? 4000 : false) });
  const done = () => { qc.invalidateQueries({ queryKey: ["jobs"] }); qc.invalidateQueries({ queryKey: ["card-images"] }); };
  const move = useMutation({ mutationFn: api.repointCatalogImages, onSettled: done });
  const back = useMutation({ mutationFn: api.restoreCatalogImages, onSettled: done });
  const err = st.error || move.error || back.error;

  return (
    <Section title="Card images" id="settings-images">
      <div className="flex flex-wrap items-center gap-2">
        {st.data && (st.data.legacy
          ? <Badge tone="warn">{st.data.legacy} cards on images.pokemontcg.io</Badge>
          : <Badge tone="ok">all cards on TCGdex or another host</Badge>)}
        <Button disabled={running || move.isPending || !st.data?.legacy} onClick={() => move.mutate()}>{running ? "Moving…" : "Move to TCGdex"}</Button>
        <Button variant="secondary" disabled={running || back.isPending || !st.data?.restorable} onClick={() => back.mutate()}>Restore old URLs ({st.data?.restorable ?? 0})</Button>
      </div>
      <p className="mt-2 text-xs text-muted">Cards TCGdex has no artwork for keep their old URL. The old URL is saved on the card, so this can be undone.</p>
      {err && <p className="mt-3 text-sm text-danger">{errorText(err)}</p>}
    </Section>);
}
