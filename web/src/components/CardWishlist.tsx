import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Heart, Trash2 } from "lucide-react";
import { api, money } from "../lib/api";
import { requestPriceFetch } from "../lib/autoFetch";
import { eurosToCents, wantLabel } from "../lib/wishlist";
import { Badge, Button, Checkbox, Field, Input, SegmentedControl, Section, Select } from "./ui";
import { GRADERS } from "./CardCollection";

const GRADES = ["10", "9.5", "9", "8.5", "8", "7.5", "7", "6", "5", "4", "3", "2", "1"];
const opts = (a: string[]) => a.map((v) => ({ value: v, label: v }));

/** Wishlist entries of one card + the form to want a version (raw or graded) with an optional target price. */
export default function CardWishlist({ card }: { card: any }) {
  const id: string = card._id ?? card.id;
  const qc = useQueryClient();
  const [f, setF] = useState({ graded: false, company: "PSA", grade: "9", target: "", alert: true });
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const up = (p: Partial<typeof f>) => setF((o) => ({ ...o, ...p }));
  const list = useQuery({ queryKey: ["wishlist", "card", id], queryFn: () => api.wishlist(id) });
  const inval = () => { qc.invalidateQueries({ queryKey: ["wishlist"] }); qc.invalidateQueries({ queryKey: ["alerts"] }); qc.invalidateQueries({ queryKey: ["cards"] }); };
  const add = useMutation({
    mutationFn: (target: number | null) => api.addWish({
      card_id: id, grading: f.graded ? { company: f.company, grade: +f.grade } : null,
      ...(target != null ? { target_price: target } : {}), alert: f.alert }),
    onSuccess: async () => {
      inval(); setErr(""); setF((o) => ({ ...o, target: "" }));
      setMsg("Saved.");
      if (await requestPriceFetch(id) === "started") setMsg("Saved. Fetching prices (see Prices > Fetch).");
    },
    onError: (e: Error) => setErr(e.message),
  });
  const del = useMutation({ mutationFn: (wid: string) => api.removeWish(wid), onSuccess: inval });
  const submit = () => {
    const cents = eurosToCents(f.target);
    if (cents === undefined) return setErr("Target must be above 0 (or empty)");
    add.mutate(cents);
  };
  const items = list.data ?? [];
  return (
    <Section title={<><Heart size={14} className="mr-1.5 inline align-[-2px]" />Wishlist{items.length ? ` (${items.length})` : ""}</>}>
      <div className="space-y-3">
        {items.length > 0 && <ul className="divide-y divide-line">
          {items.map((w) => (
            <li key={w.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
              <Badge tone={w.grading ? "accent" : "neutral"}>{wantLabel(w)}</Badge>
              <span className="num w-24 text-right">{w.needs_price ? <span className="text-muted">needs price</span> : w.value == null ? <span className="text-muted">no price</span> : <>{w.estimated && "≈ "}{money(w.value)}</>}</span>
              <span className="min-w-0 flex-1 text-muted">{w.target_price != null ? <>target <span className="num">{money(w.target_price)}</span></> : "no target"}</span>
              {w.hit && <Badge tone="ok">target hit</Badge>}
              <Button variant="ghost" size="sm" aria-label={`Remove ${wantLabel(w)} from wishlist`} disabled={del.isPending} onClick={() => del.mutate(w.id)}><Trash2 size={14} /></Button>
            </li>))}
        </ul>}
        <SegmentedControl label="Wanted version" value={f.graded ? "graded" : "raw"} onChange={(v) => up({ graded: v === "graded" })}
          options={[{ value: "raw", label: "Raw" }, { value: "graded", label: "Graded" }]} />
        <div className="flex flex-wrap items-end gap-3">
          {f.graded && <>
            <Field label="Grader"><div className="w-28"><Select aria-label="Wish grader" value={f.company} onChange={(v) => up({ company: v })} options={opts(GRADERS)} /></div></Field>
            <Field label="Grade"><div className="w-24"><Select aria-label="Wish grade" value={f.grade} onChange={(v) => up({ grade: v })} options={opts(GRADES)} /></div></Field></>}
          <Field label="Target price (€)"><div className="w-28"><Input type="number" step="0.01" min="0" value={f.target} onChange={(e) => up({ target: e.target.value })} /></div></Field>
          <Checkbox label="Alert below target" checked={f.alert} onChange={(e) => up({ alert: e.target.checked })} />
        </div>
        <div className="flex flex-wrap items-center gap-3 border-t border-line pt-3">
          <Button disabled={add.isPending} onClick={submit}><Heart size={14} />Add to wishlist</Button>
          {msg && <span className="text-sm text-muted" role="status">{msg}</span>}
          {err && <span role="alert" className="text-sm text-danger">{err}</span>}
        </div>
      </div>
    </Section>);
}
