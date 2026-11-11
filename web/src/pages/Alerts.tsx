import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Check, Pause, Play, RefreshCw, Trash2 } from "lucide-react";
import { ago, api, money, type AlertEvent, type AlertIn, type AlertRule, type WishEntry } from "../lib/api";
import { QueryError } from "../components/QueryState";
import {
  Badge, Button, Checkbox, Combobox, Drawer, EmptyState, Input, SegmentedControl, Section, Select, Skeleton,
  Table, THead, Th, Tr, Td, type ComboPage,
} from "../components/ui";

const OPS = { above: "goes above", below: "drops below", up_pct: "rises by", down_pct: "falls by" } as const;
const OP_OPTIONS = Object.entries(OPS).map(([value, label]) => ({ value, label }));
const SCOPES = [
  { value: "total", label: "my collection total" },
  { value: "card", label: "a card (all its stacks)" },
  { value: "stack", label: "a single stack" },
  { value: "wish", label: "a wishlist card" },
];
const isPct = (op: string) => op.endsWith("_pct");
const KIND_TONE: Record<string, "ok" | "neutral" | "warn"> = { sold: "ok", market: "neutral", ask: "warn" };
const PAGE = 20;

type Form = { scope: string; target: string; targetLabel: string; op: string; amount: string; days: string; kind: "any" | "sold" | "market"; est: boolean };

/** Plain-English summary of the rule being built; null while incomplete. */
export function previewRule(f: Form): string | null {
  const amount = parseFloat(f.amount);
  if (!(amount > 0)) return null;
  if (f.scope !== "total" && !f.target) return null;
  const subject = f.scope === "total" ? "your collection total" : f.targetLabel || "the selected item";
  const what = isPct(f.op) ? `${amount}% over ${parseInt(f.days, 10) || 7} days` : `EUR ${amount.toFixed(2)}`;
  const kind = f.kind === "any" ? "" : ` (${f.kind} prices only)`;
  return `You'll be alerted when ${subject} ${OPS[f.op as keyof typeof OPS]} ${what}${kind}.`;
}

function Inbox() {
  const qc = useQueryClient();
  const ev = useQuery({ queryKey: ["alerts", "events"], queryFn: () => api.alertEvents() });
  const read = useMutation({
    mutationFn: (ids?: string[]) => api.markAlertsRead(ids),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const unread = (ev.data ?? []).filter((e) => !e.read);
  const line = (e: AlertEvent) => e.type === "system"
    ? <span className="text-warn">{e.rule}</span>
    : e.type === "reprice" || e.type === "sold_comp"
    ? <span>{e.type === "sold_comp" && <Badge tone="warn" className="mr-1.5">sold elsewhere</Badge>}{e.rule} <Link className="text-accent hover:underline" to="/reprice">open reprice</Link></span>
    : <span><b>{e.name}</b>: {e.rule} <span className="text-muted">— now</span> <span className="num font-medium">{money(e.value)}</span>
      {e.prev != null && <span className="num text-muted"> (was {money(e.prev)}, {e.pct! > 0 ? "+" : ""}{e.pct}%)</span>}</span>;
  return (
    <Section title={<>Inbox{unread.length > 0 && <Badge tone="accent" className="ml-2 align-middle normal-case">{unread.length} unread</Badge>}</>}
      actions={<Button variant="secondary" size="sm" disabled={!unread.length} onClick={() => read.mutate(undefined)}><Check size={12} />Mark all read</Button>}>
      <QueryError q={ev} label="Inbox" />
      {ev.isLoading && <div className="space-y-2"><Skeleton className="h-12" /><Skeleton className="h-12" /></div>}
      {ev.data?.length === 0 && <EmptyState title="No alerts yet">Rules are checked after every price fetch, refresh and snapshot.</EmptyState>}
      <ul className="space-y-2">
        {ev.data?.map((e) => (
          <li key={e.id} className={`flex items-start justify-between gap-3 rounded-lg border border-line p-3 text-sm ${e.read ? "opacity-60" : "border-l-2 border-l-accent"}`}>
            <div className="min-w-0 space-y-1">
              <div>{line(e)}</div>
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
                <span>{ago(e.fired_at)}</span>
                {e.price_kind && <Badge tone={KIND_TONE[e.price_kind] ?? "neutral"}>{e.price_kind}</Badge>}
                {e.thin && <Badge tone="warn">thin data</Badge>}
                {e.estimated && <Badge tone="warn">estimated</Badge>}
                {e.card_id && <Link className="text-accent hover:underline" to={`/cards/${encodeURIComponent(e.card_id)}`}>open card</Link>}
              </div>
            </div>
            {!e.read && <Button variant="ghost" size="sm" onClick={() => read.mutate([e.id])}>Mark read</Button>}
          </li>))}
      </ul>
    </Section>
  );
}

/** One page of the owned stacks matching `q`, as picker options. Card scope dedupes by card_id in the Combobox. */
const stackPage = (scope: string) => async (q: string, page: number): Promise<ComboPage> => {
  const r = await api.collection({ q: q || undefined, page, page_size: PAGE });
  const items: any[] = r.items ?? [];
  const options = items.map((i) => scope === "card"
    ? { value: i.card_id as string, label: `${i.card?.name ?? i.card_id}${i.card?.number ? ` #${i.card.number}` : ""}` }
    : { value: i.id as string, label: stackLabel(i) });
  return { options, more: page * PAGE < (r.total ?? 0) };
};
const wishPage = async (q: string): Promise<ComboPage> => {
  const all = await api.wishlist();
  const needle = q.trim().toLowerCase();
  const options = all.map((w) => ({ value: w.id, label: wishLabel(w) })).filter((o) => o.label.toLowerCase().includes(needle));
  return { options, more: false };
};
export const wishLabel = (w: WishEntry) => `${w.card?.name ?? w.card_id} #${w.card?.number ?? "?"} · ${w.grading ? `${w.grading.company} ${w.grading.grade}` : "raw"}`;
const stackLabel = (i: any) =>
  `${i.card?.name ?? i.card_id} #${i.card?.number ?? "?"} · ${i.grading ? `${i.grading.company} ${i.grading.grade}` : i.condition} × ${i.quantity}`;

function RuleForm() {
  const qc = useQueryClient();
  const stackParam = useSearchParams()[0].get("stack"); // "Create alert" shortcut from Collection
  const [f, setF] = useState<Form>({ scope: stackParam ? "stack" : "total", target: stackParam ?? "", targetLabel: "", op: "above", amount: "", days: "7", kind: "any", est: false });
  const [err, setErr] = useState("");
  // the prefilled stack id has no name yet: resolve it once from the list
  const prefill = useQuery({
    queryKey: ["collection", "alert-prefill", stackParam], enabled: !!stackParam,
    queryFn: () => api.collection({ page_size: 200 }),
  });
  const found = f.target === stackParam ? (prefill.data?.items ?? []).find((i: any) => i.id === stackParam) : undefined;
  const label = f.targetLabel || (found ? stackLabel(found) : "");
  const create = useMutation({
    mutationFn: (b: AlertIn) => api.createAlert(b),
    onSuccess: () => { setErr(""); setF({ ...f, amount: "" }); qc.invalidateQueries({ queryKey: ["alerts"] }); },
    onError: (e: Error) => setErr(e.message),
  });
  const set = (p: Partial<Form>) => setF({ ...f, ...p });
  const submit = () => {
    const amount = parseFloat(f.amount);
    if (!(amount > 0)) return setErr("Enter an amount above 0");
    if (f.scope !== "total" && !f.target) return setErr("Pick a target");
    const b: AlertIn = { scope: f.scope, op: f.op, kind: f.kind, include_estimated: f.est,
      threshold: isPct(f.op) ? amount : Math.round(amount * 100) };
    if (f.scope === "stack") b.item_id = f.target;
    if (f.scope === "card") b.card_id = f.target;
    if (f.scope === "wish") b.wish_id = f.target;
    if (isPct(f.op)) b.days = parseInt(f.days, 10);
    create.mutate(b);
  };
  const preview = previewRule({ ...f, targetLabel: label });
  return (
    <Section title="New rule">
      <div className="space-y-4">
        <div className="flex flex-wrap items-end gap-x-3 gap-y-3 text-sm">
          <span className="pb-2">Alert me when</span>
          <div className="w-52"><Select aria-label="Scope" value={f.scope} options={SCOPES} onChange={(v) => set({ scope: v, target: "", targetLabel: "" })} /></div>
          {f.scope !== "total" && (
            <div className="w-72">
              <Combobox key={f.scope} aria-label={f.scope === "card" ? "Card" : f.scope === "wish" ? "Wishlist card" : "Stack"} cacheKey={`alert-${f.scope}`} value={f.target} selectedLabel={label}
                placeholder={f.scope === "card" ? "Search a card…" : f.scope === "wish" ? "Search your wishlist…" : "Search a stack…"}
                fetchPage={f.scope === "wish" ? wishPage : stackPage(f.scope)}
                onChange={(v, l) => set({ target: v, targetLabel: l })} />
            </div>)}
          <div className="w-40"><Select aria-label="Condition" value={f.op} options={OP_OPTIONS} onChange={(v) => set({ op: v })} /></div>
          <div className="w-28"><Input aria-label="Amount" inputMode="decimal" placeholder={isPct(f.op) ? "10" : "100.00"} value={f.amount} onChange={(e) => set({ amount: e.target.value })} /></div>
          <span className="pb-2 text-muted">{isPct(f.op) ? "%" : "EUR"}</span>
          {isPct(f.op) && <>
            <span className="pb-2">over</span>
            <div className="w-16"><Input aria-label="Days" inputMode="numeric" value={f.days} onChange={(e) => set({ days: e.target.value })} /></div>
            <span className="pb-2">days</span></>}
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <div className="flex items-center gap-2 text-sm"><span className="text-muted">Use</span>
            <SegmentedControl label="Price kind" value={f.kind} onChange={(v) => set({ kind: v })}
              options={[{ value: "any", label: "any price" }, { value: "sold", label: "sold only" }, { value: "market", label: "market only" }]} /></div>
          <Checkbox label="Include estimated prices" checked={f.est} onChange={(e) => set({ est: e.target.checked })} />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={create.isPending} onClick={submit}><Bell size={14} />Add rule</Button>
          <p className="text-sm text-muted" aria-live="polite">{preview ?? "Fill in the sentence above to see what this rule does."}</p>
        </div>
        {err && <p role="alert" className="text-sm text-danger">{err}</p>}
      </div>
    </Section>
  );
}

function Explainer() {
  return (
    <Section title="How alerts work" collapsible id="alerts-explainer" defaultOpen>
      <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted">
        <li>A rule watches a <b className="text-fg">stack</b>, a <b className="text-fg">wishlist card</b>, a <b className="text-fg">card</b> (all its stacks) or your <b className="text-fg">collection total</b>.</li>
        <li>Rules are checked after every price fetch, refresh and daily snapshot, or when you press <b className="text-fg">Check now</b>.</li>
        <li>A rule fires <b className="text-fg">once</b> when its condition becomes true, then re-arms when it clears. One that is already true fires on the next check.</li>
        <li>Percent rules compare against the price N days ago. Amounts are in EUR.</li>
        <li>A stack with no price never fires and never re-arms: unknown is not a change.</li>
        <li><b className="text-fg">thin data</b> = few recent sales; <b className="text-fg">estimated</b> = a nearby grade or fallback price. Estimated prices only count if you tick the option.</li>
      </ul>
    </Section>
  );
}

function Rules() {
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: ["alerts", "rules"], queryFn: api.alerts });
  const [confirm, setConfirm] = useState<AlertRule | null>(null);
  const inval = () => qc.invalidateQueries({ queryKey: ["alerts"] });
  const toggle = useMutation({ mutationFn: (r: AlertRule) => api.patchAlert(r.id, { enabled: !r.enabled }), onSuccess: inval });
  const del = useMutation({ mutationFn: (id: string) => api.deleteAlert(id), onSuccess: () => { setConfirm(null); inval(); } });
  const check = useMutation({ mutationFn: api.evaluateAlerts, onSuccess: inval });
  // same query as the nav badge: Mark read in the Inbox refetches it, which clears the label
  const unread = useQuery({ queryKey: ["alerts", "unread"], queryFn: api.alertUnread });
  const fresh = Math.min(check.data?.fired ?? 0, unread.data?.count ?? 0);
  return (
    <Section title="Rules" actions={<div className="flex items-center gap-3">
      {fresh > 0 && <span className="text-sm text-muted">{fresh} new</span>}
      <Button variant="secondary" size="sm" disabled={check.isPending} onClick={() => check.mutate()}><RefreshCw size={12} />Check now</Button></div>}>
      <QueryError q={rules} label="Rules" />
      {rules.isLoading && <Skeleton className="h-16" />}
      {rules.data?.length === 0 && <EmptyState title="No rules yet">Create one below.</EmptyState>}
      {!!rules.data?.length && (
        <Table><THead><Th>Rule</Th><Th>State</Th><Th>Last check</Th><Th className="text-right">Actions</Th></THead>
          <tbody>
            {rules.data.map((r) => (
              <Tr key={r.id} className={r.enabled ? "" : "opacity-60"}>
                <Td>{r.description}{r.include_estimated && <span className="ml-1 text-xs text-muted">(incl. estimated)</span>}</Td>
                <Td>{!r.enabled ? <Badge>disabled</Badge> : r.triggered ? <Badge tone="warn">triggered</Badge> : <Badge tone="ok">armed</Badge>}</Td>
                <Td className="num text-muted">{r.last_value != null ? `last ${money(r.last_value)}` : "not priced yet"}{r.last_pct != null ? ` (${r.last_pct}%)` : ""}</Td>
                <Td className="text-right whitespace-nowrap">
                  <Button variant="ghost" size="sm" aria-label={`${r.enabled ? "Disable" : "Enable"} rule`} onClick={() => toggle.mutate(r)}>
                    {r.enabled ? <Pause size={13} /> : <Play size={13} />}{r.enabled ? "Disable" : "Enable"}</Button>
                  <Button variant="ghost" size="sm" aria-label="Delete rule" onClick={() => setConfirm(r)}><Trash2 size={13} /></Button>
                </Td>
              </Tr>))}
          </tbody></Table>)}
      <Drawer open={!!confirm} onClose={() => setConfirm(null)} title="Delete rule?">
        <p className="mb-4 text-sm text-muted">{confirm?.description}</p>
        <div className="flex gap-2">
          <Button variant="danger" disabled={del.isPending} onClick={() => confirm && del.mutate(confirm.id)}>Delete</Button>
          <Button variant="secondary" onClick={() => setConfirm(null)}>Cancel</Button>
        </div>
      </Drawer>
    </Section>
  );
}

export default function Alerts() {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <Inbox />
      <div className="space-y-6">
        <Explainer />
        <Rules />
        <RuleForm />
      </div>
    </div>);
}
