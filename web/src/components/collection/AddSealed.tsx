import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AcquiredPatch, type SealedType } from "../../lib/api";
import AcquiredForm from "../AcquiredForm";
import { errorText } from "../QueryState";
import { Button, Combobox, Drawer, Field, Input, Select } from "../ui";

const LANGS = ["en", "ja"].map((l) => ({ value: l, label: l === "en" ? "English" : "Japanese" }));

/** Own a sealed product: pick the set from our sets list, the type and language; the app creates the catalog entry. */
export default function AddSealed({ open, onClose, onAdded }: { open: boolean; onClose: () => void; onAdded?: (r: any) => void }) {
  const qc = useQueryClient();
  const [language, setLanguage] = useState("en");
  const [setId, setSetId] = useState("");
  const [setLabel, setSetLabel] = useState("");
  const [type, setType] = useState<SealedType>("booster_box");
  const [edition, setEdition] = useState("");
  const [qty, setQty] = useState("1");
  const [acq, setAcq] = useState<AcquiredPatch>({});
  const [err, setErr] = useState<string | null>(null);
  const types = useQuery({ queryKey: ["sealed", "types"], queryFn: api.sealedTypes, staleTime: Infinity });
  const add = useMutation({
    mutationFn: () => api.addSealed({ set_id: setId, type, language, edition: edition.trim() || null, quantity: parseInt(qty, 10),
      acquired: Object.keys(acq).length ? acq : null }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["collection"] }); qc.invalidateQueries({ queryKey: ["sealed"] }); onAdded?.(r); onClose(); },
    onError: (e) => setErr(errorText(e)),
  });
  function submit() {
    const n = parseInt(qty, 10);
    if (!setId) return setErr("Pick a set");
    if (!(n >= 1)) return setErr("Quantity must be at least 1");
    setErr(null);
    add.mutate();
  }
  const fetchSets = async (q: string) => {
    const all: any[] = await api.sets(false, language);
    const t = q.toLowerCase();
    return { options: all.filter((s) => !t || s.name.toLowerCase().includes(t) || s.external_id.toLowerCase().includes(t))
      .map((s) => ({ value: s.external_id, label: `${s.name} (${s.external_id})` })), more: false };
  };
  return (
    <Drawer open={open} onClose={onClose} title="Add sealed product">
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Language"><Select aria-label="Language" value={language} onChange={(v) => { setLanguage(v); setSetId(""); setSetLabel(""); }} options={LANGS} /></Field>
          <Field label="Type"><Select aria-label="Type" value={type} onChange={(v) => setType(v as SealedType)} options={types.data ?? []} /></Field>
        </div>
        <Field label="Set">
          <Combobox aria-label="Set" cacheKey={`sealed-sets-${language}`} value={setId} selectedLabel={setLabel} placeholder="Pick a set…"
            fetchPage={fetchSets} onChange={(v, l) => { setSetId(v); setSetLabel(l); }} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Variant / contents (optional)"><Input aria-label="Edition" maxLength={80} value={edition} onChange={(e) => setEdition(e.target.value)} placeholder="Eevee promo, random promo, Costco…" /></Field>
          <Field label="Quantity"><Input aria-label="Quantity" type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} /></Field>
        </div>
        <p className="text-xs text-muted">Same type and set but different contents (promo card, retailer)? Give each its own variant: they become separate stacks with their own price.</p>
        <AcquiredForm hideSubmit initial={{ type: "purchased", price: null, currency: "EUR", date: null, source: null }} qty={parseInt(qty, 10) || 1} onChange={setAcq} />
        {err && <p role="alert" className="text-sm text-danger">{err}</p>}
        <div className="flex justify-end gap-2"><Button variant="ghost" type="button" onClick={onClose}>Cancel</Button>
          <Button type="button" disabled={add.isPending} onClick={submit}>Add to collection</Button></div>
      </div>
    </Drawer>);
}
