import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, X } from "lucide-react";
import { api, type PresetScope } from "../../lib/api";
import { presetActive } from "../../lib/urlState";
import { Button, Chip, Input } from "../ui";

type Builtin = { name: string; query: Record<string, string> };

/**
 * Saved filter presets for a list page: built-ins (shipped) + the user's own (stored in Mongo so they
 * follow the user across devices). Clicking one replaces the page's filters/sort with it.
 */
export default function PresetBar({ scope, state, defaults, keys, builtins, onApply }: {
  scope: PresetScope; state: Record<string, string>; defaults: Record<string, string>; keys: readonly string[];
  builtins: Builtin[]; onApply: (patch: Record<string, string>) => void;
}) {
  const qc = useQueryClient();
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const saved = useQuery({ queryKey: ["presets", scope], queryFn: () => api.presets(scope), staleTime: 60_000 });
  const list = Array.isArray(saved.data) ? saved.data : [];
  const refresh = () => qc.invalidateQueries({ queryKey: ["presets", scope] });
  const save = useMutation({
    mutationFn: () => api.savePreset({ name: name.trim(), scope, query: Object.fromEntries(keys.filter((k) => state[k] !== defaults[k]).map((k) => [k, state[k]])) }),
    onSuccess: () => { refresh(); setNaming(false); setName(""); },
  });
  const del = useMutation({ mutationFn: (id: string) => api.deletePreset(id), onSuccess: refresh });
  const apply = (query: Record<string, string>) => onApply({ ...Object.fromEntries(keys.map((k) => [k, defaults[k]])), ...query });
  const active = (q: Record<string, string>) => presetActive(state, defaults, q, keys);
  const changed = keys.some((k) => state[k] !== defaults[k]);

  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Presets">
      <span className="text-xs text-muted">Presets</span>
      {builtins.map((p) => <Chip key={p.name} active={active(p.query)} onClick={() => apply(p.query)}>{p.name}</Chip>)}
      {list.map((p) => (
        <span key={p.id} className="inline-flex items-center">
          <Chip active={active(p.query)} onClick={() => apply(p.query)} className="rounded-r-none border-r-0">{p.name}</Chip>
          <button type="button" aria-label={`Delete preset ${p.name}`} title="Delete preset" disabled={del.isPending}
            onClick={() => del.mutate(p.id)} className="rounded-r-full border border-line px-1.5 py-1 text-muted hover:text-danger"><X size={12} /></button>
        </span>))}
      {naming
        ? <form className="flex items-center gap-1" onSubmit={(e) => { e.preventDefault(); if (name.trim()) save.mutate(); }}>
            <div className="w-40"><Input aria-label="Preset name" autoFocus maxLength={60} placeholder="Preset name" value={name} onChange={(e) => setName(e.target.value)} /></div>
            <Button size="sm" type="submit" disabled={!name.trim() || save.isPending}>Save</Button>
            <Button size="sm" variant="ghost" type="button" onClick={() => setNaming(false)}>Cancel</Button>
          </form>
        : <Button size="sm" variant="ghost" disabled={!changed} onClick={() => { save.reset(); setNaming(true); }}><Save size={12} />Save current</Button>}
      {save.error && <span role="alert" className="text-xs text-danger">{(save.error as Error).message}</span>}
    </div>);
}
