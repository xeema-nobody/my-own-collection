import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, money } from "../lib/api";
import { Kpi, Section, Table, THead, Td, Th, Tr } from "./ui";

const pct = (r: number | null | undefined) => (r == null ? "—" : `${r >= 0 ? "+" : ""}${(r * 100).toFixed(0)}%`);
const tone = (n: number | null | undefined) => (n == null ? undefined : n >= 0 ? "ok" : "danger");

/** Dashboard: is opening sealed worth it? Hidden when nothing was ever opened (or the report fails). */
export default function OpeningRoi() {
  const q = useQuery({ queryKey: ["openings", "report"], queryFn: api.openingsReport });
  const r = q.data;
  if (!r || r.openings.length === 0) return null;
  const t = r.totals;
  return (
    <Section title="Opening ROI" id="dashboard-openings">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label="Opened net" value={t.net == null ? "—" : money(t.net)} tone={tone(t.net)}
          hint={`${pct(t.roi)} on ${t.cost == null ? "—" : money(t.cost)} cost${t.excluded_unknown_cost ? `, ${t.excluded_unknown_cost} without cost left out` : ""}`} />
        <Kpi label="Pulls value" value={t.pulls_value == null ? "—" : money(t.pulls_value)} hint={`${t.openings} opening${t.openings === 1 ? "" : "s"}, ${t.units} unit${t.units === 1 ? "" : "s"}`} />
        <Kpi label="Opened vs kept sealed" value={t.vs_kept == null ? "—" : money(t.vs_kept)} tone={tone(t.vs_kept)} hint="pulls value minus what the same units are worth sealed" />
        <Kpi label="Hit rate" value={t.hit_rate == null ? "—" : `${Math.round(t.hit_rate * 100)}%`} hint={`pulled copies worth ≥ ${money(r.hit_threshold)}`} />
      </div>
      <Table className="mt-4">
        <THead><Th>Product</Th><Th num>Opened (units)</Th><Th num>Net</Th><Th num>Kept sealed</Th><Th num>Sold sealed</Th><Th num>Sold profit</Th></THead>
        <tbody>
          {r.products.map((p) => (
            <Tr key={p.card_id}>
              <Td><Link className="hover:underline" to={`/cards/${encodeURIComponent(p.card_id)}`}>{p.name ?? p.card_id}</Link></Td>
              <Td num>{p.opened.units || "—"}</Td>
              <Td num className={p.opened.net == null ? "" : p.opened.net >= 0 ? "text-ok" : "text-danger"}>{p.opened.units ? (p.opened.net == null ? "—" : money(p.opened.net)) : "—"}</Td>
              <Td num>{p.kept.units ? `${p.kept.units} · ${money(p.kept.value)}` : "—"}</Td>
              <Td num>{p.sold.units || "—"}</Td>
              <Td num>{p.sold.units ? money(p.sold.realised) : "—"}</Td>
            </Tr>))}
        </tbody>
      </Table>
      <Table className="mt-4">
        <THead><Th>Opening</Th><Th>Date</Th><Th num>Cost</Th><Th num>Pulls</Th><Th num>Net</Th><Th num>Hits</Th><Th>Best hit</Th></THead>
        <tbody>
          {r.openings.map((o) => (
            <Tr key={o.id}>
              <Td>{o.name}{o.units > 1 ? ` ×${o.units}` : ""}</Td>
              <Td>{o.date}</Td>
              <Td num>{o.cost == null ? "—" : money(o.cost)}</Td>
              <Td num>{o.pulls_value == null ? "—" : money(o.pulls_value)}{o.unpriced > 0 && <span className="text-muted"> +{o.unpriced} unpriced</span>}</Td>
              <Td num className={o.net == null ? "" : o.net >= 0 ? "text-ok" : "text-danger"}>{o.net == null ? "—" : money(o.net)}</Td>
              <Td num>{o.hit_rate == null ? "—" : `${o.hits}/${o.priced_copies}`}</Td>
              <Td>{o.best_hit ? <Link className="hover:underline" to={`/cards/${encodeURIComponent(o.best_hit.card_id)}`}>{o.best_hit.name ?? o.best_hit.card_id} · {money(o.best_hit.value)}</Link> : "—"}</Td>
            </Tr>))}
        </tbody>
      </Table>
    </Section>);
}
