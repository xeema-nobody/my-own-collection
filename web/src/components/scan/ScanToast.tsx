import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { api, type ScanEvent } from "../../lib/api";

const START = "000000000000000000000000"; // smallest ObjectId: "everything after this"
const SHOW_MS = 6000;

/** Laptop: polls for cards added from the phone, refreshes the lists and says "added: ...". Does nothing until
 *  phone mode is set up. */
export default function ScanToast() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["scan", "status"], queryFn: api.scanStatus, staleTime: 5 * 60_000, retry: false });
  const cursor = useRef<string | null>(null);
  const [shown, setShown] = useState<ScanEvent[]>([]);
  useQuery({
    queryKey: ["scan", "events"], enabled: !!status.data?.enabled, refetchInterval: 4000, refetchIntervalInBackground: false, retry: false,
    queryFn: async () => {
      const r = await api.scanEvents(cursor.current);
      if (cursor.current === null) cursor.current = r.latest ?? START; // first look: no history, just the cursor
      else if (r.events.length) {
        cursor.current = r.latest ?? cursor.current;
        setShown((o) => [...o, ...r.events]);
        for (const k of ["collection", "cards", "card"]) qc.invalidateQueries({ queryKey: [k] });
      }
      return r;
    },
  });
  useEffect(() => {
    if (!shown.length) return;
    const t = setTimeout(() => setShown((o) => o.slice(1)), SHOW_MS);
    return () => clearTimeout(t);
  }, [shown]);
  if (!shown.length) return null;
  const e = shown[0];
  return (
    <div role="status" className="fixed bottom-4 right-4 z-50 flex max-w-sm items-start gap-2 rounded-lg border border-line bg-surface p-3 text-sm shadow-lg">
      <Check size={16} className="mt-0.5 shrink-0 text-ok" />
      <span>Added: <b>{e.label}</b>{e.quantity_after > 1 ? ` (now ${e.quantity_after})` : ""}{e.type_conflict ? ". Acquisition type differs from the existing stack." : ""}{shown.length > 1 ? ` · +${shown.length - 1} more` : ""}</span>
      <button aria-label="Dismiss" className="ml-1 text-muted hover:text-fg" onClick={() => setShown((o) => o.slice(1))}><X size={14} /></button>
    </div>);
}
