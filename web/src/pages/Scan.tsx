import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Check, ScanLine } from "lucide-react";
import { api, type ScanCard, type ScanIdentify } from "../lib/api";
import { friendlyScanError, loadChoice, saveChoice } from "../lib/scan";
import CameraCapture from "../components/scan/CameraCapture";
import CandidatePicker from "../components/scan/CandidatePicker";
import AddSheet from "../components/scan/AddSheet";
import { Button, Input } from "../components/ui";

type Step = "camera" | "pick" | "details" | "done";
const EMPTY: ScanIdentify = { text: "", confidence: "none", names: [], total: 0, cards: [] };

/** Phone page: scan -> pick the exact version -> condition -> add. Never adds before the last tap. */
export default function Scan() {
  const [step, setStep] = useState<Step>("camera");
  const [res, setRes] = useState<ScanIdentify>(EMPTY);
  const [more, setMore] = useState<{ q: string; page: number } | null>(null);
  const [card, setCard] = useState<ScanCard | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const choice = useRef(loadChoice());

  const show = (r: ScanIdentify, q: string | null, page: number) => { setRes(r); setMore(q ? { q, page } : null); setErr(null); setStep("pick"); };
  const identify = useMutation({
    mutationFn: (photo: Blob) => api.scanIdentify(photo),
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
    mutationFn: ({ body }: { body: Parameters<typeof api.scanAdd>[0]; c: ReturnType<typeof loadChoice> }) => api.scanAdd(body),
    onSuccess: (r, v) => { saveChoice(v.c); choice.current = v.c; setDone(r.label + (r.stack.quantity > 1 ? ` (now ${r.stack.quantity})` : "")); setErr(null); setStep("done"); },
    onError: (e) => setErr(friendlyScanError(e)),
  });

  const again = () => { setStep("camera"); setErr(null); setCard(null); setRes(EMPTY); };
  return (
    <main className="mx-auto max-w-lg space-y-4 px-4 py-4">
      <h1 className="flex items-center gap-2 text-lg font-semibold"><ScanLine size={20} className="text-accent" />Add a card</h1>
      {err && step !== "details" && <p role="alert" className="rounded bg-danger/15 px-3 py-2 text-sm text-danger">{err}</p>}
      {step === "camera" && (identify.isPending
        ? <p className="py-16 text-center text-muted" role="status">Reading the card…</p>
        : <CameraCapture onPhoto={(b) => identify.mutate(b)} />)}
      {step === "camera" && !identify.isPending && <CandidateSearchLink onSearch={(q) => search.mutate({ q, page: 1 })} busy={search.isPending} />}
      {step === "pick" && <CandidatePicker cards={res.cards} total={res.total} confidence={res.confidence} text={res.text} read={res.read} searching={search.isPending}
        canMore={!!more && res.cards.length < res.total}
        onPick={(c) => { setCard(c); setErr(null); setStep("details"); }}
        onSearch={(q) => search.mutate({ q, page: 1 })} onMore={() => more && search.mutate({ q: more.q, page: more.page + 1 })} onRetake={again} />}
      {step === "details" && card && <AddSheet card={card} initial={choice.current} busy={add.isPending} error={err}
        onBack={() => { setErr(null); setStep("pick"); }} onAdd={(body, c) => add.mutate({ body, c })} />}
      {step === "done" && <div className="space-y-4 py-8 text-center">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-ok/15 text-ok"><Check size={28} /></div>
        <p className="text-lg font-semibold" role="status">Added: {done}</p>
        <Button className="w-full py-3 text-base" onClick={again}>Scan the next card</Button>
      </div>}
    </main>);
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
