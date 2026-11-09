import { useState } from "react";
import { ExternalLink, TriangleAlert } from "lucide-react";
import type { CertInfo, ScanCert, ScanSlab } from "../../lib/api";
import { GRADERS } from "../../lib/scan";
import { Badge, Button, Input } from "../ui";

const TIER: Record<string, string> = { "GEM MINT": "Gem Mint", "MINT": "Mint", "NM-MT": "Near Mint-Mint", "PRISTINE": "Pristine", "BLACK LABEL": "Black Label" };
const titleCase = (s: string) => s.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
const tierText = (t?: string | null) => (t ? TIER[t.toUpperCase()] ?? titleCase(t) : "");

/** `ACE 10 Gem Mint - Radiant Charizard 011/078 - Pokemon GO 2022 - Holo - cert 158690`: what the grader's page says. */
export function certSummary(slab: ScanSlab | null | undefined, info: CertInfo | null | undefined): string {
  const grade = info?.grade ?? slab?.grade;
  const num = info?.number ? `${info.number}${info.printed_total ? `/${String(info.printed_total).padStart(info.number.length, "0")}` : ""}` : "";
  const set = [info?.set_name, info?.year].filter(Boolean).join(" ");
  return [
    [info?.grader ?? slab?.grader, grade, tierText(info?.tier ?? slab?.tier)].filter((x) => x != null && x !== "").join(" "),
    [info?.name, num].filter(Boolean).join(" "), set, info?.variant, (info?.cert ?? slab?.cert) ? `cert ${info?.cert ?? slab?.cert}` : "",
  ].filter(Boolean).join(" - ");
}

const HOW: Record<string, { tone: "ok" | "warn" | "neutral"; text: string }> = {
  exact: { tone: "ok", text: "Matches the page: confirm the print" }, likely: { tone: "warn", text: "Likely match: check the print" },
  possible: { tone: "warn", text: "Several prints fit: pick the one you hold" }, none: { tone: "neutral", text: "" },
};

/** Why a cert gave no card, in words for the phone (the page statuses of `providers/grading`). */
function problem(info: CertInfo, cards: number): string | null {
  switch (info.status) {
    case "not_found": return `${info.grader} has no record of cert ${info.cert}. Check the digits.`;
    case "invalid": return `${info.cert} is not a valid ${info.grader} cert number. Check the digits.`;
    case "blocked": case "unavailable": return `The ${info.grader} page could not be read now${info.detail ? ` (${info.detail})` : ""}. Try again, or type the card.`;
    case "link_only": return `${info.grader} has no page this app can read. Open the report and type the card.`;
    case "found": return cards === 0 ? "This card is not in the catalog (a Japanese card, or not a Pokemon card). Type the name below; the cert details above fill the slab form." : null;
    default: return null;
  }
}

/** Phone result card for a slab: what the label read and the grader's page says, the disagreements, and a way to fix grader / cert and look again. */
export default function SlabResult({ slab, result, busy, error, onLookup }: {
  slab: ScanSlab | null | undefined; result: ScanCert | null | undefined; busy?: boolean; error?: string | null; onLookup: (grader: string, cert: string) => void;
}) {
  const [grader, setGrader] = useState(result?.cert.grader ?? slab?.grader ?? "");
  const [cert, setCert] = useState(result?.cert.cert ?? slab?.cert ?? "");
  const digits = cert.replace(/\D/g, "");
  const info = result?.cert ?? null;
  const warn = result?.warnings ?? [];
  const bad = info ? problem(info, result?.cards.length ?? 0) : null;
  const summary = certSummary(slab, info?.status === "found" ? info : null);
  return (
    <section aria-label="Slab result" className="space-y-2 rounded-lg border border-line bg-surface p-3 text-sm">
      {summary ? <p className="font-semibold">{summary}</p> : <p className="font-medium">The label could not be read. Pick the grader and type the cert number.</p>}
      {slab?.grader && slab.grader_seen === false && <p className="text-xs text-muted">The grader is a guess from the label layout: check it.</p>}
      {info?.status === "found" && result && HOW[result.how_exact].text && result.cards.length > 0 && <Badge tone={HOW[result.how_exact].tone}>{HOW[result.how_exact].text}</Badge>}
      {warn.map((w) => <p key={w.code} role="alert" className="flex items-start gap-1.5 rounded bg-warn/15 px-2 py-1.5 text-warn">
        <TriangleAlert size={14} className="mt-0.5 shrink-0" /><span>{w.text}: check the cert digits.</span></p>)}
      {bad && <p role="status" className="text-muted">{bad}</p>}
      {result?.report_url && <a className="inline-flex items-center gap-1 text-accent underline" href={result.report_url} target="_blank" rel="noreferrer">Open {info?.grader} report<ExternalLink size={12} /></a>}
      <form className="space-y-2 border-t border-line pt-2" aria-label="Edit grader and cert"
        onSubmit={(e) => { e.preventDefault(); if (grader && grader !== "OTHER" && digits) onLookup(grader, digits); }}>
        <div className="grid grid-cols-5 gap-1.5" role="radiogroup" aria-label="Grader">
          {GRADERS.filter(([v]) => v !== "OTHER").map(([v, l]) => <Button key={v} type="button" variant={v === grader ? "primary" : "secondary"} role="radio" aria-checked={v === grader} onClick={() => setGrader(v)}>{l}</Button>)}
        </div>
        <div className="flex gap-2">
          <Input aria-label="Cert number" inputMode="numeric" placeholder="Cert number" maxLength={20} value={cert} onChange={(e) => setCert(e.target.value)} />
          <Button type="submit" variant="secondary" disabled={busy || !grader || !digits}>{busy ? "Looking…" : result ? "Look up again" : "Look up"}</Button>
        </div>
        {error && <p role="alert" className="text-danger">{error}</p>}
      </form>
    </section>);
}
