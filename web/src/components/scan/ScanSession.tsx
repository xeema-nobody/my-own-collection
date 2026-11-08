import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Gem, Smartphone, Undo2 } from "lucide-react";
import { api, type ScanEvent, type ScanSession as Session } from "../../lib/api";
import { Button } from "../ui";

const START = "000000000000000000000000";

function Thumb({ cardId }: { cardId: string }) {
  const q = useQuery({ queryKey: ["card", cardId], queryFn: () => api.card(cardId), staleTime: 5 * 60_000, retry: false });
  const img = q.data?.images?.small;
  return img ? <img src={img} alt="" className="h-16 rounded" /> : <div className="h-16 w-11 rounded bg-surface-2" />;
}

/** Laptop: "Start a scan" opens a session the phone picks up on its own; what the phone adds is shown here as it happens. */
export default function ScanSession() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["scan", "status"], queryFn: api.scanStatus, staleTime: 60_000, retry: false });
  const [session, setSession] = useState<Session | null>(null);
  const [events, setEvents] = useState<ScanEvent[]>([]);
  const cursor = useRef<string>(START);
  const start = useMutation({
    mutationFn: (mode: "raw" | "slab") => api.scanStartSession(mode),
    onSuccess: (s) => { cursor.current = START; setEvents([]); setSession(s); },
  });
  const close = useMutation({
    mutationFn: (id: string) => api.scanCloseSession(id),
    onSettled: () => { setSession(null); setEvents([]); },
  });
  useQuery({
    queryKey: ["scan", "session-events", session?.id], enabled: !!session, refetchInterval: 2000, retry: false,
    queryFn: async () => {
      const r = await api.scanEvents(cursor.current, session!.id);
      if (r.events.length) {
        cursor.current = r.latest ?? cursor.current;
        setEvents((o) => [...o, ...r.events]);
        for (const k of ["collection", "cards", "card"]) qc.invalidateQueries({ queryKey: [k] });
      }
      return r;
    },
  });
  if (!status.data?.enabled) return null; // phone mode not set up: PhoneLink explains how
  if (!session) return (
    <div className="space-y-2 text-sm">
      <p>Pick what you are about to scan, then hold it up to your phone. The page on the phone is already linked and follows your choice.</p>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => start.mutate("raw")} disabled={start.isPending}><Smartphone size={14} />Scan raw cards</Button>
        <Button variant="secondary" onClick={() => start.mutate("slab")} disabled={start.isPending}><Gem size={14} />Scan slabs</Button>
      </div>
      {start.error && <p role="alert" className="text-danger">{(start.error as Error).message}</p>}
    </div>);
  const adds = events.filter((e) => e.kind !== "undo" && !events.some((u) => u.undoes === e.id));
  return (
    <div className="space-y-3 text-sm" aria-label="Scan session">
      <p role="status" className="flex items-center gap-2 text-accent"><Smartphone size={14} />
        {session.mode === "slab" ? "Slab session" : "Raw session"}: {adds.length ? `${adds.length} added this session` : "waiting for the phone… open the scan page on your phone."}</p>
      {events.length > 0 && <ul className="space-y-2">
        {events.map((e) => e.kind === "undo"
          ? <li key={e.id} className="flex items-center gap-2 text-muted"><Undo2 size={14} />Undone: {e.label}</li>
          : <li key={e.id} className="flex items-center gap-3 rounded border border-line p-2">
              <Thumb cardId={e.card_id} />
              <div className="min-w-0 flex-1"><div className="flex items-center gap-1 font-medium"><Check size={14} className="text-ok" />{e.label}</div>
                <div className="text-xs text-muted">{e.condition ?? "graded"} · {e.language ?? "en"} · now {e.quantity_after}{e.type_conflict ? " · acquisition type differs from the stack" : ""}</div></div>
            </li>)}
      </ul>}
      <div className="flex gap-2">
        <Button variant="secondary" onClick={() => close.mutate(session.id)}>Finish</Button>
      </div>
    </div>);
}
