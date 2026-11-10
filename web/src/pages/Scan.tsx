import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Laptop, ScanLine, Undo2 } from "lucide-react";
import { api, type PhotoKind, type ScanCard, type ScanIdentify } from "../lib/api";
import { EXTRA_SHOTS, friendlyScanError, loadChoice, loadMode, loadSavePhoto, saveChoice, saveMode, saveSavePhoto, type ScanMode } from "../lib/scan";
import CameraCapture from "../components/scan/CameraCapture";
import CandidatePicker from "../components/scan/CandidatePicker";
import AddSheet from "../components/scan/AddSheet";
import SlabResult from "../components/scan/SlabResult";
import JaImportPrompt from "../components/scan/JaImportPrompt";
import { Button, Input } from "../components/ui";

type Step = "camera" | "pick" | "details" | "done" | "review" | "extra";
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
  const [mode, setModeState] = useState<ScanMode>(loadMode); // remembered; slab = taller guide, label always read, slab form
  const slabMode = mode === "slab";
  const setMode = (m: ScanMode) => { setModeState(m); saveMode(m); };
  const choice = useRef(loadChoice());
  const [batch, setBatchState] = useState(() => { try { return localStorage.getItem(BATCH_KEY) === "1"; } catch { return false; } });
  const [rows, setRows] = useState<Row[]>([]);
  const [last, setLast] = useState<Row | null>(null); // the add on the "done" screen, for undo
  const [lastStack, setLastStack] = useState<{ id: string; kind: "raw" | "slab" } | null>(null);
  const setBatch = (v: boolean) => { setBatchState(v); try { localStorage.setItem(BATCH_KEY, v ? "1" : "0"); } catch { /* ignore */ } };
  // The laptop may have opened a session: poll (react-query pauses this while the page is hidden). No session = normal page.
  const sess = useQuery({ queryKey: ["scan", "session"], queryFn: api.scanSession, refetchInterval: 2500, retry: false });
  const sessionId = sess.data?.session?.id ?? null;
  const sessionMode = sess.data?.session?.mode ?? null;
  // A NEW session sets the mode the laptop chose, in memory only (the device default stays as saved). After that the
  // phone toggle wins until the next new session; a session that vanishes leaves the mode alone.
  const appliedId = useRef<string | null>(null);
  useEffect(() => {
    if (sessionId && sessionId !== appliedId.current) { appliedId.current = sessionId; if (sessionMode) setModeState(sessionMode); }
  }, [sessionId, sessionMode]);

  const lastPhoto = useRef<Blob | null>(null);   // kept so the match can run again after a Japanese set import
  const [savePhoto, setSavePhotoState] = useState(loadSavePhoto);
  const setSavePhoto = (v: boolean) => { setSavePhotoState(v); saveSavePhoto(v); };
  const [photoNote, setPhotoNote] = useState<string | null>(null);
  const [extra, setExtra] = useState<{ stackId: string; kind: "raw" | "slab"; i: number } | null>(null); // guided extra shots after an add
  const keepPhoto = useMutation({
    mutationFn: ({ stackId, photo, kind }: { stackId: string; photo: Blob; kind: PhotoKind }) => api.scanPhoto(stackId, photo, kind),
    onError: () => setPhotoNote("The card was added, but its photo could not be saved."),
  });
  const [jaDone, setJaDone] = useState<string | null>(null);
  const show = (r: ScanIdentify, q: string | null, page: number) => { setRes(r); setMore(q ? { q, page } : null); setErr(null); setStep("pick"); };
  const identify = useMutation({
    mutationFn: (photo: Blob) => { lastPhoto.current = photo; return api.scanIdentify(photo, slabMode); },
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
      setPhotoNote(null);
      const slabAdd = !!r.event.grading;
      if (savePhoto && lastPhoto.current && !r.stack.duplicate) keepPhoto.mutate({ stackId: r.stack.id, photo: lastPhoto.current, kind: slabAdd ? "slab_front" : "front" });
      setLastStack(r.stack.duplicate ? null : { id: r.stack.id, kind: slabAdd ? "slab" : "raw" });
      const row: Row = { eventId: r.event.id, label: r.label, condition: r.event.grading ? null : v.c.condition, quantity: r.stack.quantity };
      setDone(r.stack.duplicate ? `${r.label}: already in your collection, nothing changed` : r.label + (r.stack.quantity > 1 ? ` (now ${r.stack.quantity})` : "")); setErr(null);
      if (!r.stack.duplicate) { setLast(row); setRows((o) => [...o, row]); }
      setCard(null); setRes(EMPTY);
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
  // Slab result card: fix the grader / cert and look again; the answer replaces the cards and the label read.
  const relookup = useMutation({
    mutationFn: ({ grader, cert }: { grader: string; cert: string }) => api.scanCert(grader, cert, { grade: res.slab?.grade, tier: res.slab?.tier }),
    onSuccess: (got, v) => {
      setRes((o) => ({ ...o, cert: got, cards: got.cards, total: got.cards.length, names: got.cert.name ? [got.cert.name] : [], text: "",
        slab: { ...(o.slab ?? { grade: null }), grader: v.grader, cert: v.cert, grader_seen: true } }));
      setMore(null); setErr(null);
    },
    onError: (e) => setErr(friendlyScanError(e)),
  });
  const lastRow = rows[rows.length - 1] ?? null;
  const slabForSheet = res.slab ? { ...res.slab, grade: res.slab.grade ?? res.cert?.cert.grade ?? null } : slabMode ? { grader: null, grade: null, cert: null } : null;
  const showSlab = slabMode && !!(res.slab || res.cert || res.cards.length === 0);
  const again = () => { setStep("camera"); setErr(null); setCard(null); setRes(EMPTY); setJaDone(null); };
  // Nothing matched after a photo / typed number: offer the likely Japanese set (catalog import), then match again.
  const offerJa = step === "pick" && res.cards.length === 0 && !!(res.read || res.cert) && !identify.isPending && !relookup.isPending && !search.isPending;
  const rematch = (set: string) => {
    setJaDone(set);
    const c = res.cert?.cert;
    if (slabMode && c?.grader && c.cert) relookup.mutate({ grader: c.grader, cert: c.cert });
    else if (lastPhoto.current) identify.mutate(lastPhoto.current);
  };
  return (
    <main className="mx-auto max-w-lg space-y-4 px-4 py-4">
      <h1 className="flex items-center gap-2 text-lg font-semibold"><ScanLine size={20} className="text-accent" />Add a card</h1>
      {sessionId && <p role="status" className="flex items-center gap-2 rounded bg-accent/15 px-3 py-2 text-sm text-accent"><Laptop size={16} />Linked to your computer ({sessionMode === "slab" ? "slabs" : "raw cards"}): the card you pick shows up there.</p>}
      {err && step !== "details" && !(step === "pick" && showSlab) && <p role="alert" className="rounded bg-danger/15 px-3 py-2 text-sm text-danger">{err}</p>}
      {step === "camera" && (identify.isPending
        ? <p className="py-16 text-center text-muted" role="status">Reading the card…</p>
        : <div className="space-y-3">
          <div role="radiogroup" aria-label="Scan mode" className="mx-auto flex max-w-sm gap-1 rounded-lg bg-surface-2 p-1 text-sm">
            {(["raw", "slab"] as const).map((m) => (
              <button key={m} type="button" role="radio" aria-checked={mode === m} onClick={() => setMode(m)}
                className={`flex-1 rounded-md px-3 py-2 font-medium ${mode === m ? "bg-accent text-accent-fg" : "text-muted"}`}>{m === "raw" ? "Scan raw" : "Scan slab"}</button>))}
          </div>
          <CameraCapture mode={mode} onPhoto={(b) => identify.mutate(b)} />
        </div>)}
      {step === "camera" && !identify.isPending && <CandidateSearchLink onSearch={(q) => search.mutate({ q, page: 1 })} busy={search.isPending} />}
      {step === "camera" && !identify.isPending && <ManualEntry busy={lookup.isPending} onLookup={(number, set) => lookup.mutate({ number, set })} />}
      {step === "camera" && !identify.isPending && (
        <div className="space-y-2 border-t border-line pt-3">
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
      {step === "pick" && res.detected && !slabMode && (
        <div role="status" className="flex items-center gap-2 rounded bg-accent/15 px-3 py-2 text-sm text-accent">
          <span className="flex-1">Looks like a slab (graded card in a case).</span>
          <Button size="sm" onClick={() => { setMode("slab"); again(); }}>Switch to slab and retake</Button>
        </div>)}
      {step === "pick" && showSlab &&
        <SlabResult key={`${res.slab?.grader}:${res.slab?.cert}:${res.cert?.cert.status}`} slab={res.slab} result={res.cert} busy={relookup.isPending} error={err}
          onLookup={(grader, cert) => relookup.mutate({ grader, cert })} />}
      {offerJa && <JaImportPrompt key={`${res.read?.set_code}:${res.cert?.cert.cert}:${jaDone}`} code={res.read?.set_code} total={res.read?.printed_total ?? res.cert?.cert.printed_total}
        setName={res.cert?.cert.set_name} importedSet={jaDone} onImported={rematch} />}
      {step === "pick" && <CandidatePicker quiet={slabMode && !!(res.slab || res.cert)} initialQuery={res.cert?.cert.name ?? undefined} cards={res.cards} total={res.total} confidence={res.confidence} text={res.text} read={res.read} searching={search.isPending}
        canMore={!!more && res.cards.length < res.total}
        onPick={(c) => { setCard(c); setErr(null); setStep("details"); }}
        onSearch={(q) => search.mutate({ q, page: 1 })} onMore={() => more && search.mutate({ q: more.q, page: more.page + 1 })} onRetake={again} />}
      {step === "details" && card && <AddSheet card={card} initial={choice.current} reportUrl={res.cert?.report_url} busy={add.isPending} error={err} slab={slabForSheet}
        onBack={() => { setErr(null); setStep("pick"); }} onAdd={(body, c) => add.mutate({ body, c })}
        {...(lastPhoto.current ? { savePhoto, onSavePhoto: setSavePhoto } : {})} />}
      {step === "extra" && extra && <div className="space-y-3">
        <h2 className="text-base font-semibold">{EXTRA_SHOTS[extra.kind][extra.i][1]}</h2>
        <p className="text-sm text-muted">Photo {extra.i + 1} of {EXTRA_SHOTS[extra.kind].length}. It is kept with the card for listings.</p>
        {keepPhoto.isPending
          ? <p className="py-12 text-center text-muted" role="status">Saving…</p>
          : <CameraCapture mode={extra.kind} onPhoto={(b) => keepPhoto.mutate({ stackId: extra.stackId, photo: b, kind: EXTRA_SHOTS[extra.kind][extra.i][0] as PhotoKind }, {
            onSuccess: () => { if (extra.i + 1 < EXTRA_SHOTS[extra.kind].length) setExtra({ ...extra, i: extra.i + 1 }); else { setExtra(null); setStep("done"); } } })} />}
        {photoNote && <p role="alert" className="rounded bg-danger/15 px-3 py-2 text-sm text-danger">{photoNote}</p>}
        <div className="flex gap-2">
          {extra.i + 1 < EXTRA_SHOTS[extra.kind].length && <Button variant="secondary" className="flex-1" onClick={() => setExtra({ ...extra, i: extra.i + 1 })}>Skip this one</Button>}
          <Button variant="ghost" className="flex-1" onClick={() => { setExtra(null); setStep("done"); }}>Done with photos</Button>
        </div>
      </div>}
      {step === "done" && <div className="space-y-4 py-8 text-center">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-ok/15 text-ok"><Check size={28} /></div>
        <p className="text-lg font-semibold" role="status">{done?.includes("already in your collection") ? done : `Added: ${done}`}</p>
        {photoNote && <p role="alert" className="rounded bg-danger/15 px-3 py-2 text-sm text-danger">{photoNote}</p>}
        {lastStack && <Button variant="secondary" className="w-full" onClick={() => { setPhotoNote(null); setExtra({ stackId: lastStack.id, kind: lastStack.kind, i: 0 }); setStep("extra"); }}>Add more photos (back, corners)</Button>}
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
