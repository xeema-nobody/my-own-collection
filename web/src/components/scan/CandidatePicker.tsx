import { useState } from "react";
import { TriangleAlert } from "lucide-react";
import { money, type ScanCard, type ScanIdentify, type ScanRead } from "../../lib/api";
import { Badge, Button, Input } from "../ui";

const CONF: Record<ScanIdentify["confidence"], { tone: "ok" | "warn" | "neutral"; text: string }> = {
  high: { tone: "ok", text: "Name read clearly" }, medium: { tone: "warn", text: "Name read with some doubt" },
  low: { tone: "warn", text: "Name is a guess, check carefully" }, none: { tone: "neutral", text: "" },
};
const VARIANT_LABEL: Record<string, string> = { holofoil: "Holo", reverseHolofoil: "Reverse holo", normal: "Normal", "1stEditionHolofoil": "1st Edition holo", "1stEditionNormal": "1st Edition", unlimitedHolofoil: "Unlimited holo" };

function Version({ c, first, onPick }: { c: ScanCard; first: boolean; onPick: (c: ScanCard) => void }) {
  return (
    <li>
      <button type="button" onClick={() => onPick(c)} aria-label={`${c.name}, ${c.set.name} ${c.number ?? ""}`}
        className="flex h-full w-full flex-col gap-1.5 rounded-lg border border-line bg-surface p-2 text-left transition hover:border-accent focus-visible:border-accent">
        {c.image ? <img src={c.image} alt="" loading="lazy" className="mx-auto aspect-[63/88] w-full rounded object-contain" /> : <div className="aspect-[63/88] w-full rounded bg-surface-2" />}
        <div className="flex flex-wrap gap-1">
          {first && <Badge tone="accent">Most likely</Badge>}
          {c.match_label && (c.signals?.length ?? 0) > 1 && <Badge tone="ok">{c.match_label.replace(/ match$/, "")}</Badge>}
          {c.owned_qty > 0 && <Badge tone="ok">Own {c.owned_qty}</Badge>}
        </div>
        <div className="text-sm font-semibold leading-tight">{c.name}</div>
        <div className="text-xs text-muted">{c.set.name}{c.year ? ` · ${c.year}` : ""}<br />#{c.number}{c.printed_total ? `/${c.printed_total}` : ""}{c.rarity ? ` · ${c.rarity}` : ""}</div>
        {c.variants.length > 0 && <div className="flex flex-wrap gap-1">{c.variants.map((v) => <Badge key={v} tone="neutral">{VARIANT_LABEL[v] ?? v}</Badge>)}</div>}
        {c.edition_note && <div className="flex items-start gap-1 rounded bg-warn/15 px-1.5 py-1 text-xs text-warn"><TriangleAlert size={12} className="mt-0.5 shrink-0" />
          <span>Also exists as {c.edition_note}. The catalog can't tell them apart: check the stamp.</span></div>}
        <div className="num mt-auto text-sm font-semibold">{c.price != null ? money(c.price) : <span className="font-normal text-muted">no price</span>}</div>
      </button>
    </li>);
}

/** The first card is "most likely" only when it agrees on more signals than the second (or nothing was read beyond the name). */
const leads = (cards: ScanCard[]) => cards.length < 2 || (cards[0].signals?.length ?? 0) > (cards[1].signals?.length ?? 0) || !cards[0].signals?.some((x) => x !== "name");
const readText = (r?: ScanRead | null) => r ? [r.number ? `#${r.number}${r.printed_total ? `/${r.printed_total}` : ""}` : null, r.set_code].filter(Boolean).join(" · ") : "";

/** Every plausible version side by side. Nothing is added from here: tapping a card only opens the details step. */
export default function CandidatePicker({ cards, total, confidence, text, read, searching, canMore, quiet, initialQuery, onPick, onSearch, onMore, onRetake }: {
  cards: ScanCard[]; total: number; confidence: ScanIdentify["confidence"]; text: string; read?: ScanRead | null; searching?: boolean; canMore?: boolean;
  /** Slab result: the grader's page, not the photo, named the card; hide the name-read wording. `initialQuery` prefills the typed search. */
  quiet?: boolean; initialQuery?: string;
  onPick: (c: ScanCard) => void; onSearch: (q: string) => void; onMore: () => void; onRetake: () => void;
}) {
  const [q, setQ] = useState(initialQuery ?? "");
  const conf = CONF[confidence];
  return (
    <div className="space-y-3">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim().length >= 2) onSearch(q.trim()); }}>
        <Input aria-label="Type the card name" placeholder="Type the card name" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button type="submit" variant="secondary" disabled={searching || q.trim().length < 2}>Search</Button>
      </form>
      {cards.length === 0
        ? <div className="space-y-2 rounded-lg border border-line bg-surface p-4 text-sm">
            <p className="font-medium">{quiet ? "No card from the catalog yet." : "Couldn't read a card name."}</p>
            {quiet ? <p className="text-muted">Type the card name above and search; nothing is added until you tap Add.</p>
              : <p className="text-muted">Move closer, reduce glare, keep the name at the top, or type it above.{text ? ` (Read: "${text}")` : ""}</p>}
          </div>
        : <>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              {!quiet && conf.text && <Badge tone={conf.tone}>{conf.text}</Badge>}
              {readText(read) && <Badge tone="neutral">Read {readText(read)}</Badge>}
              <span className="text-muted">{total > cards.length ? `Showing ${cards.length} of ${total} versions` : `${cards.length} version${cards.length === 1 ? "" : "s"}`}. Tap the one you hold.</span>
            </div>
            <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">{cards.map((c, i) => <Version key={c.id} c={c} first={i === 0 && confidence !== "none" && leads(cards)} onPick={onPick} />)}</ul>
            {canMore && <Button variant="secondary" className="w-full" disabled={searching} onClick={onMore}>Show more versions</Button>}
          </>}
      <div className="flex gap-2">
        <Button variant="ghost" className="flex-1" onClick={onRetake}>None of these, scan again</Button>
      </div>
    </div>);
}
