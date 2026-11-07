import { useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Laptop, ScanLine, Undo2 } from "lucide-react";
import { api, type ScanCard, type ScanIdentify } from "../lib/api";
import { friendlyScanError, loadChoice, saveChoice } from "../lib/scan";
import CameraCapture from "../components/scan/CameraCapture";
import CandidatePicker from "../components/scan/CandidatePicker";
import AddSheet from "../components/scan/AddSheet";
import { Button, Input } from "../components/ui";

type Step = "camera" | "pick" | "details" | "done" | "review";
type Row = { eventId: string; label: string; condition: string | null; quantity: number };
const BATCH_KEY = "scan.batch";
const EMPTY: ScanIdentify = { text: "", confidence: "none", names: [], total: 0, cards: [] };

/** Phone page: scan -> pick the exact version -> condition -> add. Never adds before the last tap. */
export default function Scan() {
  const [step, setStep] = useState<Step>("camera");
  const [res, setRes] = useState<ScanIdentify>(EMPTY);
  const [more, setMore] = useState<{ q: string; page: number } | null>(null);
  const [card, setCard] = useState<ScanCard | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [slabMode, setSlabMode] = useState(false); // "this is a slab": also read the label, open the slab form
  const choice = useRef(loadChoice());
  const [batch, setBatchState] = useState(() => { try { return localStorage.getItem(BATCH_KEY) === "1"; } catch { return false; } });
  const [rows, setRows] = useState<Row[]>([]);
  const [last, setLast] = useState<Row | null>(null); // the add on the "done" screen, for undo
  const setBatch = (v: boolean) => { setBatchState(v); try { localStorage.setItem(BATCH_KEY, v ? "1" : "0"); } catch { /* ignore */ } };
  // The laptop may have opened a session: poll (react-query pauses this while the page is hidden). No session = normal page.
  const sess = useQuery({ queryKey: ["scan", "session"], queryFn: api.scanSession, refetchInterval: 2500, retry: false });
  const sessionId = sess.data?.session?.id ?? null;

  const show = (r: ScanIdentify, q: string | null, page: number) => { setRes(r); setMore(q ? { q, page } : null); setErr(null); setStep("pick"); };
  const identify = useMutation({
    mutationFn: (photo: Blob) => api.scanIdentify(photo, slabMode),
    onSuccess: (r) => show(r, r.names[0] ?? null, 0),
    onError: (e) => setErr(friendlyScanError(e)),
  });
  const search = useMutation({
    mutationFn: ({ q, page }: { q: string; page: number }) => api.scanSearch(q, page),
    onSuccess: (r, v) => {
      if (v.page === 1) show({ ...EMPTY, confidence: r.cards.length ? "low" : "none", total: r.total, cards: r.cards, names: [v.q] }, v.q, 1);
      else {
        setRes((o) => {
          const cards = [...o.cards, ...r.cards.filter((c) => !o.cards.some((x) => x.id === c.id))];
          return { ...o, cards, total: cards.length === o.cards.length ? cards.length : o.total }; // nothing new: stop offering more
        });
        setMore({ q: v.q, page: v.page });
      }
    },
    onError: (e) => setErr(friendlyScanError(e)),
  });
  const add = useMutation({
    mutationFn: ({ body }: { body: Parameters<typeof api.scanAdd>[0]; c: ReturnType<typeof loadChoice> }) => api.scanAdd(body, sessionId),
    onSuccess: (r, v) => {
      saveChoice(v.c); choice.current = v.c;
      const row: Row = { eventId: r.event.id, label: r.label, condition: r.event.grading ? null : v.c.condition, quantity: r.stack.quantity };
      setDone(r.stack.duplicate ? `${r.label}: already in your collection, nothing changed` : r.label + (r.stack.quantity > 1 ? ` (now ${r.stack.quantity})` : "")); setErr(null);
      if (!r.stack.duplicate) { setLast(row); setRows((o) => [...o, row]); }
      setCard(null); setRes(EMPTY); setSlabMode(false);
      setStep(batch ? "camera" : "done"); // batch: straight back to the camera for the next card
    },
    onError: (e) => setErr(friendlyScanError(e)),
  });

  const undo = useMutation({
    mutationFn: (row: Row) => api.scanUndo(row.eventId),
    onSuccess: (_r, row) => { setRows((o) => o.filter((x) => x.eventId !== row.eventId)); setLast(null); setErr(null); setStep("camera"); },
    onError: (e) => setErr(friendlyScanError(e)),
  });
  const lookup = useMutation({
    mutationFn: ({ number, set }: { number: string; set: string }) => api.scanLookup(number, set),
    onSuccess: (r) => show(r, null, 0),
    onError: (e) => setErr(friendlyScanError(e)),
  });
  const lastRow = rows[rows.length - 1] ?? null;
  const again = () => { setStep("camera"); setErr(null); setCard(null); setRes(EMPTY); };
  return (
    <main className="mx-auto max-w-lg space-y-4 px-4 py-4">
      <h1 className="flex items-center gap-2 text-lg font-semibold"><ScanLine size={20} className="text-accent" />Add a card</h1>
      {sessionId && <p role="status" className="flex items-center gap-2 rounded bg-accent/15 px-3 py-2 text-sm text-accent"><Laptop size={16} />Linked to your computer: the card you pick shows up there.</p>}
      {err && step !== "details" && <p role="alert" className="rounded bg-danger/15 px-3 py-2 text-sm text-danger">{err}</p>}
      {step === "camera" && (identify.isPending
        ? <p className="py-16 text-center text-muted" role="status">Reading the card…</p>
        : <CameraCapture onPhoto={(b) => identify.mutate(b)} />)}
      {step === "camera" && !identify.isPending && <CandidateSearchLink onSearch={(q) => search.mutate({ q, page: 1 })} busy={search.isPending} />}
      {step === "camera" && !identify.isPending && <ManualEntry busy={lookup.isPending} onLookup={(number, set) => lookup.mutate({ number, set })} />}
      {step === "camera" && !identify.isPending && (
        <div className="space-y-2 border-t border-line pt-3">
          <label className="flex items-center justify-between gap-3 text-sm">
            <span><b>This is a slab</b><span className="block text-xs text-muted">Graded card in a case: also reads the label (grader, grade, cert).</span></span>
            <input type="checkbox" role="switch" aria-label="This is a slab" className="h-5 w-5" checked={slabMode} onChange={(e) => setSlabMode(e.target.checked)} />
          </label>
          <label className="flex items-center justify-between gap-3 text-sm">
            <span><b>Batch mode</b><span className="block text-xs text-muted">After each add, the camera is ready for the next card.</span></span>
            <input type="checkbox" role="switch" aria-label="Batch mode" className="h-5 w-5" checked={batch} onChange={(e) => setBatch(e.target.checked)} />
          </label>
          {rows.length > 0 && <div className="flex items-center gap-2 rounded bg-surface-2 px-3 py-2 text-sm">
            <span className="flex-1" role="status">{rows.length} added{lastRow ? <> · last: {lastRow.label}</> : null}</span>
            <Button variant="secondary" size="sm" disabled={undo.isPending || !lastRow} onClick={() => lastRow && undo.mutate(lastRow)}><Undo2 size={12} />Undo last</Button>
            <Button variant="secondary" size="sm" onClick={() => setStep("review")}>Review</Button>
          </div>}
        </div>)}
      {step === "review" && <div className="space-y-3">
        <h2 className="text-base font-semibold">{rows.length} added</h2>
        {rows.length === 0 ? <p className="text-muted">Nothing added yet.</p> : (
          <ul className="divide-y divide-line rounded border border-line text-sm">
            {rows.map((r) => <li key={r.eventId} className="flex items-center justify-between gap-2 px-3 py-2"><span>{r.label}</span><span className="text-muted">{r.condition ?? ""}{r.quantity > 1 ? ` · now ${r.quantity}` : ""}</span></li>)}
          </ul>)}
        <div className="flex gap-2">
          <Button variant="secondary" className="flex-1" disabled={!lastRow || undo.isPending} onClick={() => lastRow && undo.mutate(lastRow)}><Undo2 size={14} />Undo last</Button>
          <Button className="flex-1" onClick={() => { setRows([]); setLast(null); again(); }}>Finish</Button>
        </div>
        <Button variant="ghost" className="w-full" onClick={again}>Keep scanning</Button>
      </div>}
      {step === "pick" && <CandidatePicker cards={res.cards} total={res.total} confidence={res.confidence} text={res.text} read={res.read} searching={search.isPending}
        canMore={!!more && res.cards.length < res.total}
        onPick={(c) => { setCard(c); setErr(null); setStep("details"); }}
        onSearch={(q) => search.mutate({ q, page: 1 })} onMore={() => more && search.mutate({ q: more.q, page: more.page + 1 })} onRetake={again} />}
      {step === "details" && card && <AddSheet card={card} initial={choice.current} busy={add.isPending} error={err} slab={res.slab ?? (slabMode ? { grader: null, grade: null, cert: null } : null)}
        onBack={() => { setErr(null); setStep("pick"); }} onAdd={(body, c) => add.mutate({ body, c })} />}
      {step === "done" && <div className="space-y-4 py-8 text-center">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-ok/15 text-ok"><Check size={28} /></div>
        <p className="text-lg font-semibold" role="status">{done?.includes("already in your collection") ? done : `Added: ${done}`}</p>
        <Button className="w-full py-3 text-base" onClick={again}>Scan the next card</Button>
        {last && <Button variant="ghost" className="w-full" disabled={undo.isPending} onClick={() => undo.mutate(last)}><Undo2 size={14} />Undo this add</Button>}
      </div>}
    </main>);
}

/** Typed fallback when the photo cannot be read: collector number (127/182) and, to narrow it, a set code or name. */
function ManualEntry({ onLookup, busy }: { onLookup: (number: string, set: string) => void; busy: boolean }) {
  const [num, setNum] = useState("");
  const [set, setSet] = useState("");
  return (
    <form className="mx-auto max-w-sm space-y-2" aria-label="Type number and set"
      onSubmit={(e) => { e.preventDefault(); if (num.trim()) onLookup(num.trim(), set.trim()); }}>
      <p className="text-xs text-muted">Or type what is printed at the bottom of the card:</p>
      <div className="flex gap-2">
        <Input aria-label="Card number" placeholder="127/182" inputMode="text" value={num} onChange={(e) => setNum(e.target.value)} />
        <Input aria-label="Set code or name" placeholder="Set (PAR, Jungle)" value={set} onChange={(e) => setSet(e.target.value)} />
        <Button type="submit" variant="secondary" disabled={busy || !num.trim()}>Find</Button>
      </div>
    </form>);
}

/** Type-the-name shortcut under the camera, for when scanning is not an option. */
function CandidateSearchLink({ onSearch, busy }: { onSearch: (q: string) => void; busy: boolean }) {
  const [q, setQ] = useState("");
  return (
    <form className="mx-auto flex max-w-sm gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 2) onSearch(q.trim()); }}>
      <Input aria-label="Or type the card name" placeholder="Or type the card name" value={q} onChange={(e) => setQ(e.target.value)} />
      <Button type="submit" variant="secondary" disabled={busy || q.trim().length < 2}>Search</Button>
    </form>);
}
