import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, money, type PublishEntry } from "../../lib/api";
import { Button, Skeleton } from "../ui";

export type QueueAct = "cancel" | "retry" | "release";
const STATE_LABEL: Record<string, string> = { confirmed: "Waiting", publishing: "Publishing", published: "Published", failed: "Failed", cancelled: "Cancelled" };

/** Publish queue (6e): what the Claude session will work, is working, or has finished. Confirming a row is the approval; Cancel withdraws it. */
export function QueueList({ entries, busy, onAct, title = "Vinted publish queue" }: { entries: PublishEntry[]; busy: boolean; onAct: (id: string, a: QueueAct) => void; title?: string }) {
  return (
    <section aria-label="Publish queue" className="space-y-1 rounded-lg border border-line p-3">
      <h3 className="font-medium">{title}</h3>
      {entries.slice(-30).reverse().map((q) => (
        <div key={q.id} className="flex flex-wrap items-center gap-2 text-xs">
          <span className="w-20 text-muted">{STATE_LABEL[q.state] ?? q.state}</span>
          <span className="min-w-0 flex-1 truncate">{q.payload.title} · {money(q.payload.price, q.payload.currency)}{q.mode === "update" ? " · update" : ""}</span>
          {q.error && <span className="text-danger">{q.error}</span>}
          {q.url && q.state === "published" && <a className="text-accent underline" href={q.url} target="_blank" rel="noreferrer">item</a>}
          {q.state === "confirmed" && <Button size="sm" variant="secondary" disabled={busy} onClick={() => onAct(q.id, "cancel")}>Cancel</Button>}
          {q.state === "publishing" && <Button size="sm" variant="secondary" disabled={busy} onClick={() => onAct(q.id, "release")}>Release</Button>}
          {q.state === "failed" && <Button size="sm" variant="secondary" disabled={busy} onClick={() => onAct(q.id, "retry")}>Retry</Button>}
        </div>))}
    </section>);
}

/** Opens Vinted's create page in a new tab of this browser; the Vinted publisher extension sees the hash and works the queue there. */
export const VINTED_PUBLISH_URL = "https://www.vinted.nl/items/new#moc-publish";

/** Settings > Data: every queue entry (all states), with Cancel / Release / Retry. The Claude session works "Waiting" ones one at a time. */
export default function PublishQueueView() {
  const qc = useQueryClient();
  const queue = useQuery({ queryKey: ["publish-queue", "all"], refetchInterval: 5000, queryFn: () => api.publishQueue() });
  const act = useMutation({ mutationFn: ({ id, a }: { id: string; a: QueueAct }) => api.publishAct(id, a),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["publish-queue"] }) });
  if (queue.isLoading) return <Skeleton className="h-16 w-full" />;
  if (queue.error) return <p role="alert" className="text-sm text-danger">{String((queue.error as Error).message)}</p>;
  if (!queue.data?.length) return <p className="text-sm text-muted">Nothing queued. Confirm a stack with "Publish on Vinted" in the collection drawer.</p>;
  const waiting = queue.data.filter((q) => q.state === "confirmed").length;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={!waiting} onClick={() => window.open(VINTED_PUBLISH_URL, "_blank")}>Publish waiting{waiting ? ` (${waiting})` : ""}</Button>
        <span className="text-xs text-muted">Needs the Vinted publisher extension (extension/README.md). Its popup sets dry run.</span>
      </div>
      <QueueList entries={queue.data} busy={act.isPending} onAct={(id, a) => act.mutate({ id, a })} title="Queue" />
    </div>);
}
