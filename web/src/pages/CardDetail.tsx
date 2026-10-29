import { requestPriceFetch } from "../lib/autoFetch";
import { QueryError } from "../components/QueryState";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import PriceChart from "../components/PriceChart";
import PriceMatrix from "../components/PriceMatrix";
import CardFetch from "../components/CardFetch";
import SourceStatus from "../components/SourceStatus";
import SalesList from "../components/SalesList";
import SourceCompare from "../components/SourceCompare";
import { Section } from "../components/ui";
import { usePriceGrade } from "../lib/priceGrade";

const CONDITIONS = ["NM", "LP", "MP", "HP", "DMG"];
const LANGS = ["en", "ja", "es", "it", "fr", "de", "pt", "ko", "zh"];
const GRADERS = ["PSA", "BGS", "CGC", "SGC", "ACE", "OTHER"];

export default function CardDetail() {
  const id = decodeURIComponent(useParams().id!);
  const qc = useQueryClient();
  const card = useQuery({ queryKey: ["card", id], queryFn: () => api.card(id) });
  const matches = useQuery({ queryKey: ["match", id], queryFn: () => api.cardMatches(id) });
  const owned = useQuery({ queryKey: ["owned-values", id], queryFn: () => api.ownedItems(id) });
  const rawCompare = useQuery({ queryKey: ["compare", id], queryFn: () => api.cardCompare(id) });
  const [f, setF] = useState({ variant: "", language: "en", graded: false, condition: "NM", company: "PSA", grade: "9", cert: "", qty: "1", price: "", notes: "" });
  const add = useMutation({
    mutationFn: () => api.addToCollection({
      card_id: id, variant: f.variant || card.data.variants[0] || null, language: f.language,
      condition: f.graded ? null : f.condition,
      grading: f.graded ? { company: f.company, grade: +f.grade, cert_number: f.cert || null } : null,
      quantity: +f.qty, notes: f.notes || null,
      acquired: f.price ? { price: Math.round(+f.price * 100), currency: "EUR" } : null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["card", id] }); qc.invalidateQueries({ queryKey: ["collection"] }); autoFetch(); },
  });
  const pg = usePriceGrade(id);
  const [fetchMsg, setFetchMsg] = useState("");
  // Best-effort: adding never waits for or fails because of the price fetch.
  const autoFetch = async () => {
    setFetchMsg("Saved. Fetching prices…");
    const r = await requestPriceFetch(id);
    qc.invalidateQueries({ queryKey: ["jobs"] });
    setFetchMsg({ started: "Saved. Fetching prices (see Prices > Fetch).", queued: "Saved. Another price fetch is running; this card is queued.",
      offline: "Saved. Prices not fetched: fetcher offline (the stack shows “needs price”).", error: "Saved. Prices not fetched." }[r]);
  };
  const dec = useMutation({
    mutationFn: ({ sid, del }: { sid: string; del?: boolean }) => del ? api.deleteItem(sid) : api.removeFromCollection(sid, 1),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["card", id] }),
  });
  const inc = useMutation({ mutationFn: (s: any) => api.addToCollection({ card_id: id, variant: s.variant, language: s.language, condition: s.condition, grading: s.grading, quantity: 1 }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["card", id] }); autoFetch(); } });

  if (card.isLoading) return <p>Loading…</p>;
  if (card.error) return <QueryError q={card} label="Card" />;
  const c = card.data;
  const field = (label: string, el: React.ReactNode) => <label className="block text-sm">{label}{el}</label>;
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  return (
    <div className="grid gap-8 md:grid-cols-[340px_1fr]">
      <img src={c.images?.large} alt={c.name} className="w-full max-w-sm self-start rounded-lg shadow-card md:sticky md:top-20" />
      <div className="max-w-5xl space-y-5">
        <div><h1 className="text-3xl font-semibold tracking-tight">{c.name}</h1>
          <p className="text-muted">{c.set?.name} · #{c.number}/{c.set?.printed_total} · {c.rarity} · {c.types?.join(", ")}</p>
          {c.flavor_text && <p className="mt-1 text-sm italic">{c.flavor_text}</p>}</div>

        <Section title="Prices" collapsible id="card-prices">
          <CardFetch cardId={id} />
          <h3 className="mb-1 text-sm font-semibold">Compare sources</h3>
          <div className="mb-3 space-y-3">
            <div><div className="mb-1 text-xs text-muted">Raw copy (one)</div>{rawCompare.data ? <SourceCompare row={rawCompare.data} matches={matches.data} /> : <p className="text-sm text-muted">Loading…</p>}</div>
            {(owned.data?.items ?? []).filter((i: any) => i.grading).map((i: any) => (
              <div key={i.id}><div className="mb-1 text-xs text-muted">Owned: {i.grading.company} {i.grading.grade} × {i.quantity} (stack value)</div><SourceCompare row={i} matches={matches.data} /></div>))}
          </div>
          <PriceMatrix pg={pg} />
        </Section>

        <Section title="Sources" collapsible id="card-sources" defaultOpen={false}><SourceStatus cardId={id} /></Section>

        <SalesList sales={c.sales ?? []} stats={c.sales_stats ?? []} />

        <Section title="Price history" collapsible id="card-history"><PriceChart cardId={id} pg={pg} /></Section>

        <Section title="Owned">
          {c.owned.length === 0 && <p className="text-sm text-muted">None yet.</p>}
          {c.owned.map((s: any) => (
            <div key={s.id} className="flex items-center gap-2 border-b border-line py-2 text-sm last:border-0">
              <span className="flex-1">{s.variant ? `${s.variant} · ` : ""}{s.language.toUpperCase()} · {s.grading ? `${s.grading.company} ${s.grading.grade}` : s.condition}</span>
              <button className="btn-ghost" onClick={() => dec.mutate({ sid: s.id })}>−</button>
              <span className="w-6 text-center">{s.quantity}</span>
              <button className="btn-ghost" disabled={!!s.grading?.cert_number} onClick={() => inc.mutate(s)}>+</button>
              <button className="btn-ghost" onClick={() => dec.mutate({ sid: s.id, del: true })}>Remove</button>
            </div>))}
        </Section>

        <Section title="Add to collection">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {c.variants.length > 1 && field("Variant", <select className="input w-full" value={f.variant} onChange={set("variant")}>{c.variants.map((v: string) => <option key={v}>{v}</option>)}</select>)}
            {field("Language", <select className="input w-full" value={f.language} onChange={set("language")}>{LANGS.map((v) => <option key={v}>{v}</option>)}</select>)}
            <label className="flex items-end gap-2 text-sm"><input type="checkbox" checked={f.graded} onChange={set("graded")} />Graded</label>
            {!f.graded ? field("Condition", <select className="input w-full" value={f.condition} onChange={set("condition")}>{CONDITIONS.map((v) => <option key={v}>{v}</option>)}</select>)
              : <>{field("Grader", <select className="input w-full" value={f.company} onChange={set("company")}>{GRADERS.map((v) => <option key={v}>{v}</option>)}</select>)}
                {field("Grade", <input className="input w-full" type="number" step="0.5" min="1" max="10" value={f.grade} onChange={set("grade")} />)}
                {field("Cert #", <input className="input w-full" value={f.cert} onChange={set("cert")} />)}</>}
            {field("Quantity", <input className="input w-full" type="number" min="1" value={f.qty} onChange={set("qty")} />)}
            {field("Price paid (€)", <input className="input w-full" type="number" step="0.01" value={f.price} onChange={set("price")} />)}
            {field("Notes", <input className="input w-full" value={f.notes} onChange={set("notes")} />)}
          </div>
          <button className="btn mt-3" disabled={add.isPending} onClick={() => add.mutate()}>Add</button>
          {add.error && <span className="ml-3 text-sm text-danger">{String(add.error)}</span>}
          {fetchMsg && <span className="ml-3 text-sm opacity-80" role="status">{fetchMsg}</span>}
          {add.isSuccess && <span className="ml-3 text-sm text-ok">Added</span>}
        </Section>
      </div>
    </div>
  );
}
