import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, RefreshCw } from "lucide-react";
import { api, money, type RepriceRow } from "../lib/api";
import { QueryError } from "../components/QueryState";
import ListingPackDrawer from "../components/collection/ListingPackDrawer";
import { Badge, Button, EmptyState, Input, Section, Skeleton, Table, THead, Th, Tr, Td } from "../components/ui";

const cents = (s: string) => { const n = Math.round(parseFloat(s.replace(",", ".")) * 100); return Number.isFinite(n) && n > 0 ? n : null; };
const euros = (c: number | null) => (c === null ? "" : (c / 100).toFixed(2));
const key = (r: RepriceRow) => `${r.item_id}:${r.platform}`;

/** Roadmap 6d: listed stacks, market vs asking, suggested = market + markup. Confirm saves the price in the app only. */
export default function Reprice() {
  const qc = useQueryClient();
  const t = useQuery({ queryKey: ["reprice"], queryFn: api.reprice });
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [packIds, setPackIds] = useState<string[]>([]);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["reprice"] }); qc.invalidateQueries({ queryKey: ["alerts"] }); };
  const confirm = useMutation({
    mutationFn: ({ r, price }: { r: RepriceRow; price: number }) => api.repriceConfirm({ item_id: r.item_id, platform: r.platform, asking_price: price }),
    onSuccess: refresh });
  const run = useMutation({ mutationFn: api.repriceEvaluate, onSuccess: refresh });
  const value = (r: RepriceRow) => edits[key(r)] ?? euros(r.suggested);

  return (
    <div className="space-y-4">
      <Section title="Reprice listed cards"
        actions={<Button variant="secondary" size="sm" disabled={run.isPending} onClick={() => run.mutate()}><RefreshCw size={12} />Check now</Button>}>
        <p className="mb-3 text-sm text-muted">
          Suggested price = market + {t.data?.markup_pct ?? 10} %. Confirm saves the new asking price here only; nothing is sent to a marketplace.
          Update the platform afterwards ("Update on Vinted" has its own confirm).
        </p>
        <QueryError q={t} label="Reprice table" />
        {t.isLoading && <Skeleton className="h-24" />}
        {t.data && t.data.rows.length === 0 && <EmptyState title="Nothing listed">Cards with status Listed show up here.</EmptyState>}
        {run.data && <p className="mb-2 text-xs text-muted">{run.data.price_moves} price move(s), {run.data.sold_comps} new sold comp(s) added to the inbox.</p>}
        {confirm.isError && <p role="alert" className="mb-2 text-sm text-danger">{(confirm.error as Error).message}</p>}
        {t.data && t.data.rows.length > 0 && (
          <Table>
            <THead><Th>Card</Th><Th>Platform</Th><Th>Asking</Th><Th>Market</Th><Th>Change</Th><Th>Suggested</Th><Th>Last sold</Th><Th>{""}</Th></THead>
            <tbody>
              {t.data.rows.map((r) => {
                const price = cents(value(r));
                const big = r.change_pct !== null && Math.abs(r.change_pct) >= (t.data?.threshold_pct ?? 5);
                return (
                  <Tr key={key(r)}>
                    <Td><Link className="text-accent hover:underline" to={`/cards/${encodeURIComponent(r.card_id)}`}>{r.name}</Link>
                      <div className="text-xs text-muted">{r.set} {r.number}{r.grade_key !== "raw" ? ` · ${r.grade_key}` : ""}{r.quantity > 1 ? ` · x${r.quantity}` : ""}</div></Td>
                    <Td>{r.url ? <a className="text-accent hover:underline" href={r.url} target="_blank" rel="noreferrer">{r.platform}</a> : r.platform}</Td>
                    <Td className="num">{money(r.asking_price, r.currency)}</Td>
                    <Td className="num">{r.market === null ? <span className="text-muted">no price</span> : money(r.market)}</Td>
                    <Td className="num">{r.change_pct === null ? "—" : <span className={big ? "text-warn" : "text-muted"}>{r.change_pct > 0 ? "+" : ""}{r.change_pct}%</span>}</Td>
                    <Td><Input aria-label={`Suggested ${r.name} ${r.platform}`} className="w-24" inputMode="decimal" value={value(r)} placeholder="price"
                      onChange={(e) => setEdits((x) => ({ ...x, [key(r)]: e.target.value }))} /></Td>
                    <Td className="text-xs">{r.last_sold ? <>{money(r.last_sold.price, r.last_sold.currency ?? "EUR")} <span className="text-muted">{r.last_sold.source} {r.last_sold.sold_at}</span>
                      {r.last_sold.condition_unknown && <Badge tone="warn" className="ml-1">condition unknown</Badge>}</> : <span className="text-muted">—</span>}</Td>
                    <Td className="whitespace-nowrap">
                      {r.needs_platform_update && <Badge tone="warn" className="mr-2">update on {r.platform}</Badge>}
                      <Button size="sm" disabled={price === null || price === r.asking_price || confirm.isPending}
                        onClick={() => confirm.mutate({ r, price: price! })}><Check size={12} />Confirm</Button>
                      {r.platform === "vinted" && r.needs_platform_update &&
                        <Button size="sm" variant="secondary" className="ml-2" onClick={() => setPackIds([r.item_id])}>Update on Vinted</Button>}
                    </Td>
                  </Tr>);
              })}
            </tbody>
          </Table>)}
      </Section>
      <ListingPackDrawer ids={packIds} open={packIds.length > 0} onClose={() => { setPackIds([]); refresh(); }} />
    </div>
  );
}
