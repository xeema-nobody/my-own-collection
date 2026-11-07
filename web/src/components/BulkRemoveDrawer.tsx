import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type BulkRemoveResult, type ExitReason } from "../lib/api";
import { Button, Drawer, Field, Input, SegmentedControl } from "./ui";

const REASONS: { value: ExitReason; label: string }[] = [
  { value: "sold", label: "Sold" }, { value: "gifted", label: "Gifted" }, { value: "removed", label: "Just remove" }];

/** Confirm + run a bulk removal. Collection stacks keep a history row each (one reason for all); wishlist entries
 *  are plain deletes (their alerts go too). Shows the per-entry result, so a partial failure is never hidden. */
export default function BulkRemoveDrawer({ kind, ids, copies, open, onClose, onDone, onChanged }: {
  /** onChanged: data changed (refetch); onDone: drawer closed after a removal (clear the selection) */
  kind: "stacks" | "wishes"; ids: string[]; copies?: number; open: boolean; onClose: () => void; onDone: () => void; onChanged: () => void;
}) {
  const [reason, setReason] = useState<ExitReason>("removed");
  const [note, setNote] = useState("");
  const n = ids.length;
  const word = kind === "stacks" ? (n === 1 ? "stack" : "stacks") : (n === 1 ? "wishlist entry" : "wishlist entries");
  const m = useMutation<BulkRemoveResult>({
    mutationFn: () => kind === "stacks" ? api.bulkRemoveStacks(ids, reason, note.trim() || null) : api.bulkRemoveWishes(ids),
    onSuccess: () => onChanged(),
  });
  const close = () => { const done = !!m.data; m.reset(); onClose(); if (done) onDone(); };
  const r = m.data;
  return (
    <Drawer open={open} onClose={close} title={`Remove ${n} ${word}?`}>
      {!r && <div className="space-y-3 text-sm">
        {kind === "stacks" ? <>
          <p>Removes {n} {word}{copies != null ? ` (${copies} cop${copies === 1 ? "y" : "ies"} in total)` : ""} from the collection. Each one is kept in the exit history, so nothing is lost silently.</p>
          <SegmentedControl label="Reason" value={reason} onChange={setReason} options={REASONS} />
          <Field label="Note (optional)"><Input aria-label="Note" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Who / where" /></Field>
          {reason === "sold" && <p className="text-xs text-muted">Sale prices are not recorded in bulk; use Sell / remove on a stack to add one.</p>}
        </> : <p>Removes {n} {word}. Their target alerts are deleted too.</p>}
        {m.error && <p role="alert" className="text-danger">{(m.error as Error).message}</p>}
        <div className="flex gap-2">
          <Button variant="danger" disabled={m.isPending} onClick={() => m.mutate()}>Remove {n}</Button>
          <Button variant="secondary" onClick={close}>Cancel</Button>
        </div>
      </div>}
      {r && <div className="space-y-3 text-sm" role="status">
        <p className={r.failed ? "text-warn" : "text-ok"}>Removed {r.removed}{r.copies != null ? ` (${r.copies} copies)` : ""}{r.failed ? `, ${r.failed} failed` : ""}.</p>
        {r.failed > 0 && <ul className="list-disc pl-5 text-muted">{r.results.filter((x) => !x.ok).map((x) => <li key={x.id}>{x.id}: {x.error}</li>)}</ul>}
        <Button onClick={close}>Close</Button>
      </div>}
    </Drawer>);
}
