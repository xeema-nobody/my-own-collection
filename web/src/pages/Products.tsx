import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { api, money, type Product, type ProductIn, type ProductStatus, type ProductType } from "../lib/api";
import { QueryError, errorText } from "../components/QueryState";
import { Badge, Button, Drawer, EmptyState, Field, Input, Kpi, Select, SegmentedControl, Skeleton, Table, THead, Td, Th, Tr } from "../components/ui";

const TYPES: { value: ProductType; label: string }[] = [
  { value: "booster_box", label: "Booster box" }, { value: "booster_bundle", label: "Booster bundle" }, { value: "etb", label: "Elite Trainer Box" },
  { value: "booster_pack", label: "Booster pack" }, { value: "tin", label: "Tin" }, { value: "collection_box", label: "Collection box" },
  { value: "blister", label: "Blister" }, { value: "other", label: "Other" }];
const STATUSES: { value: ProductStatus; label: string }[] = [
  { value: "sealed", label: "Sealed" }, { value: "opened", label: "Opened" }, { value: "sold_sealed", label: "Sold sealed" }];
const LANGS = ["en", "ja", "es", "it", "fr", "de", "pt", "ko", "zh"].map((l) => ({ value: l, label: l.toUpperCase() }));
const TONE = { sealed: "ok", opened: "neutral", sold_sealed: "warn" } as const;
const typeLabel = (t: string) => TYPES.find((x) => x.value === t)?.label ?? t;

/** "12.50" -> 1250 cents; "" -> null; anything else -> NaN (rejected by the form). */
export function toCents(v: string): number | null {
  const t = v.trim().replace(",", ".");
  if (t === "") return null;
  return /^\d+(\.\d{1,2})?$/.test(t) ? Math.round(parseFloat(t) * 100) : NaN;
}
const fromCents = (c: number | null) => (c == null ? "" : (c / 100).toFixed(2));

type Form = { name: string; type: ProductType; set_name: string; language: string; quantity: string; status: ProductStatus;
  purchase_price: string; purchase_date: string; purchased_from: string; market_value: string; sold_price: string; note: string };

const blank = (): Form => ({ name: "", type: "booster_box", set_name: "", language: "en", quantity: "1", status: "sealed", purchase_price: "",
  purchase_date: "", purchased_from: "", market_value: "", sold_price: "", note: "" });
const fromProduct = (p: Product): Form => ({ name: p.name, type: p.type, set_name: p.set_name ?? "", language: p.language, quantity: String(p.quantity),
  status: p.status, purchase_price: fromCents(p.purchase_price), purchase_date: p.purchase_date ?? "", purchased_from: p.purchased_from ?? "",
  market_value: fromCents(p.market_value), sold_price: fromCents(p.sold_price), note: p.note ?? "" });

function ProductForm({ initial, onDone, id }: { initial: Form; onDone: () => void; id?: string }) {
  const qc = useQueryClient();
  const [f, setF] = useState(initial);
  const [err, setErr] = useState<string | null>(null);
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((x) => ({ ...x, [k]: v }));
  const save = useMutation({
    mutationFn: (b: ProductIn) => (id ? api.patchProduct(id, b) : api.addProduct(b)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["products"] }); onDone(); },
    onError: (e) => setErr(errorText(e)),
  });
  function submit() {
    const money3 = { purchase_price: toCents(f.purchase_price), market_value: toCents(f.market_value), sold_price: toCents(f.sold_price) };
    const qty = parseInt(f.quantity, 10);
    if (!f.name.trim()) return setErr("Name is required");
    if (!(qty >= 1)) return setErr("Quantity must be at least 1");
    if (Object.values(money3).some((v) => Number.isNaN(v) || v === 0)) return setErr("Prices must be positive amounts like 12.50 (leave empty if unknown)");
    setErr(null);
    save.mutate({ name: f.name.trim(), type: f.type, set_name: f.set_name.trim() || null, language: f.language, quantity: qty, status: f.status,
      ...money3, purchase_date: f.purchase_date || null, purchased_from: f.purchased_from.trim() || null, note: f.note.trim() || null });
  }
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <Field label="Name"><Input value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="Obsidian Flames Booster Box" /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Type"><Select aria-label="Type" value={f.type} onChange={(v) => set("type", v as ProductType)} options={TYPES} /></Field>
        <Field label="Status"><Select aria-label="Status" value={f.status} onChange={(v) => set("status", v as ProductStatus)} options={STATUSES} /></Field>
        <Field label="Set (free text)"><Input value={f.set_name} onChange={(e) => set("set_name", e.target.value)} /></Field>
        <Field label="Language"><Select aria-label="Language" value={f.language} onChange={(v) => set("language", v)} options={LANGS} /></Field>
        <Field label="Quantity"><Input type="number" min={1} value={f.quantity} onChange={(e) => set("quantity", e.target.value)} /></Field>
        <Field label="Market value per unit (€)"><Input inputMode="decimal" value={f.market_value} onChange={(e) => set("market_value", e.target.value)} placeholder="manual" /></Field>
        <Field label="Paid per unit (€)"><Input inputMode="decimal" value={f.purchase_price} onChange={(e) => set("purchase_price", e.target.value)} /></Field>
        <Field label="Purchase date"><Input type="date" value={f.purchase_date} onChange={(e) => set("purchase_date", e.target.value)} /></Field>
        <Field label="Bought from"><Input value={f.purchased_from} onChange={(e) => set("purchased_from", e.target.value)} /></Field>
        {f.status === "sold_sealed" && <Field label="Sold per unit (€)"><Input inputMode="decimal" value={f.sold_price} onChange={(e) => set("sold_price", e.target.value)} /></Field>}
      </div>
      <Field label="Note"><Input value={f.note} onChange={(e) => set("note", e.target.value)} /></Field>
      {err && <p role="alert" className="text-sm text-danger">{err}</p>}
      <div className="flex justify-end gap-2"><Button variant="ghost" type="button" onClick={onDone}>Cancel</Button><Button type="submit" disabled={save.isPending}>Save</Button></div>
    </form>);
}

export default function Products() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<"all" | ProductStatus>("all");
  const [edit, setEdit] = useState<{ id?: string; form: Form } | null>(null);
  const [confirm, setConfirm] = useState<Product | null>(null);
  const list = useQuery({ queryKey: ["products", "list", status], queryFn: () => api.products(status === "all" ? undefined : status) });
  const sum = useQuery({ queryKey: ["products", "summary"], queryFn: api.productsSummary });
  const move = useMutation({ mutationFn: (v: { id: string; status: ProductStatus }) => api.patchProduct(v.id, { status: v.status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["products"] }) });
  const del = useMutation({ mutationFn: (id: string) => api.removeProduct(id), onSuccess: () => { setConfirm(null); qc.invalidateQueries({ queryKey: ["products"] }); } });
  const s = sum.data;
  const rows = list.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Products</h1>
          <p className="text-sm text-muted">Sealed boxes, ETBs, packs and more. Values are entered by hand and kept apart from the card Value.</p>
        </div>
        <Button onClick={() => setEdit({ form: blank() })}><Plus size={14} aria-hidden /> Add product</Button>
      </div>
      <QueryError q={list} label="Products" /><QueryError q={sum} label="Summary" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label="Sealed value" value={money(s?.value)} hint={s && s.unpriced > 0 ? `${s.unpriced} stack${s.unpriced === 1 ? "" : "s"} without value` : undefined} />
        <Kpi label="Sealed cost" value={money(s?.cost)} hint={s && s.cost_missing > 0 ? `${s.cost_missing} stack${s.cost_missing === 1 ? "" : "s"} without cost` : undefined} />
        <Kpi label="Sealed units" value={s?.units ?? "—"} />
        <Kpi label="Sealed stacks" value={s?.stacks ?? "—"} />
      </div>
      <SegmentedControl label="Status" value={status} onChange={setStatus}
        options={[{ value: "all", label: "All" }, ...STATUSES]} />
      {list.isLoading && <Skeleton className="h-40 w-full" />}
      {list.data && rows.length === 0 && <EmptyState title="No products">Add a booster box, ETB or pack to track it.</EmptyState>}
      {rows.length > 0 && (
        <Table>
          <THead><Th>Name</Th><Th>Type</Th><Th num>Qty</Th><Th num>Paid / unit</Th><Th num>Value / unit</Th><Th num>Total value</Th><Th>Status</Th><Th><span className="sr-only">Actions</span></Th></THead>
          <tbody>
            {rows.map((p) => (
              <Tr key={p.id}>
                <Td><div className="font-medium">{p.name}</div><div className="text-xs text-muted">{[p.set_name, p.language.toUpperCase()].filter(Boolean).join(" · ")}</div></Td>
                <Td>{typeLabel(p.type)}</Td>
                <Td num>{p.quantity}</Td>
                <Td num>{money(p.purchase_price)}</Td>
                <Td num>{money(p.market_value)}</Td>
                <Td num>{p.market_value == null ? "—" : money(p.market_value * p.quantity)}</Td>
                <Td>
                  <div className="flex items-center gap-2">
                    <Badge tone={TONE[p.status]}>{STATUSES.find((x) => x.value === p.status)?.label}</Badge>
                    <Select aria-label={`Status of ${p.name}`} className="w-32" value={p.status} options={STATUSES} onChange={(v) => move.mutate({ id: p.id, status: v as ProductStatus })} />
                  </div>
                </Td>
                <Td>
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" aria-label={`Edit ${p.name}`} onClick={() => setEdit({ id: p.id, form: fromProduct(p) })}><Pencil size={14} aria-hidden /></Button>
                    <Button variant="ghost" aria-label={`Delete ${p.name}`} onClick={() => setConfirm(p)}><Trash2 size={14} aria-hidden /></Button>
                  </div>
                </Td>
              </Tr>))}
          </tbody>
        </Table>)}

      <Drawer open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? "Edit product" : "Add product"}>
        {edit && <ProductForm key={edit.id ?? "new"} id={edit.id} initial={edit.form} onDone={() => setEdit(null)} />}
      </Drawer>
      <Drawer open={!!confirm} onClose={() => setConfirm(null)} title="Delete product?">
        <p className="mb-4 text-sm text-muted">{confirm?.name} ×{confirm?.quantity} is deleted for good. To keep the history, set it to Opened or Sold sealed instead.</p>
        {del.isError && <p role="alert" className="mb-2 text-sm text-danger">{errorText(del.error)}</p>}
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setConfirm(null)}>Cancel</Button>
          <Button variant="danger" disabled={del.isPending} onClick={() => confirm && del.mutate(confirm.id)}>Delete</Button></div>
      </Drawer>
    </div>);
}
