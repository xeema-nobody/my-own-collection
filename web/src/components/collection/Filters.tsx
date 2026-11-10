import { useEffect, useState } from "react";
import { ACQ_TYPES } from "../AcquiredForm";
import { type CollectionFacets, type FacetValue, type Platform } from "../../lib/api";
import { PLATFORM_LABEL } from "./SalePanel";
import { FILTER_KEYS, SORT_OPTIONS, type CollectionParams } from "../../lib/collectionList";
import { Button, Checkbox, Input, Select, SegmentedControl } from "../ui";

const opts = (a: FacetValue[] | undefined, fallback: string[] = [], label?: (v: string) => string) =>
  (a?.length ? a.map((e) => ({ value: e.value, label: `${e.label ?? (label ? label(e.value) : e.value)} (${e.count})` }))
    : fallback.map((v) => ({ value: v, label: label ? label(v) : v })));

/** Search + filter controls of the Collection list. Options come from the facets (counts); fixed lists are the fallback. */
export default function Filters({ f, set, facets, dir, onDir }: {
  f: CollectionParams; set: (p: Partial<CollectionParams>) => void; facets?: Partial<CollectionFacets>;
  dir: "asc" | "desc"; onDir: (d: "asc" | "desc") => void;
}) {
  // typing is local; the URL (and the request) follow 300 ms after the last keystroke
  const [text, setText] = useState(f.q);
  useEffect(() => setText(f.q), [f.q]);
  useEffect(() => {
    if (text === f.q) return;
    const t = setTimeout(() => set({ q: text }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `set` is a fresh closure every render
  }, [text, f.q]);
  const dirty = FILTER_KEYS.some((k) => f[k] !== "");
  const clear = () => set(Object.fromEntries(FILTER_KEYS.map((k) => [k, ""])) as Partial<CollectionParams>);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end gap-2">
        <div className="w-56"><Input aria-label="Search owned" placeholder="Search name or number…" value={text} onChange={(e) => setText(e.target.value)} /></div>
        <div className="w-48"><Select aria-label="Set" value={f.set} onChange={(v) => set({ set: v })} allLabel="Any set" options={opts(facets?.sets)} /></div>
        <div className="w-44"><Select aria-label="Rarity" value={f.rarity} onChange={(v) => set({ rarity: v })} allLabel="Any rarity" options={opts(facets?.rarities)} /></div>
        <div className="w-36"><Select aria-label="Card type" value={f.type} onChange={(v) => set({ type: v })} allLabel="Any type" options={opts(facets?.types)} /></div>
        <div className="w-40"><Select aria-label="Type" value={f.graded} onChange={(v) => set({ graded: v, ...(v === "false" ? { grader: "", grade: "" } : {}) })} allLabel="Raw + graded"
          options={[{ value: "false", label: "Raw" }, { value: "true", label: "Graded" }]} /></div>
        <div className="w-36"><Select aria-label="Grader" value={f.grader} onChange={(v) => set({ grader: v })} allLabel="Any grader" options={opts(facets?.graders)} /></div>
        <div className="w-32"><Select aria-label="Grade" value={f.grade} onChange={(v) => set({ grade: v })} allLabel="Any grade" options={opts(facets?.grades)} /></div>
        <div className="w-40"><Select aria-label="Condition" value={f.condition} onChange={(v) => set({ condition: v })} allLabel="Any condition"
          options={opts(facets?.conditions, ["NM", "LP", "MP", "HP", "DMG"])} /></div>
        <div className="w-40"><Select aria-label="Language" value={f.language} onChange={(v) => set({ language: v })} allLabel="Any language"
          options={opts(facets?.languages, ["en", "ja", "es", "it", "fr", "de", "pt", "ko", "zh"], (v) => v.toUpperCase())} /></div>
        <div className="w-44"><Select aria-label="Acquired how" value={f.acquisition} onChange={(v) => set({ acquisition: v })} allLabel="Any acquisition"
          options={[...ACQ_TYPES, { value: "unset", label: "Not set" }]} /></div>
        <div className="w-36"><Select aria-label="Profit or loss" value={f.pl} onChange={(v) => set({ pl: v })} allLabel="Any P/L"
          options={[{ value: "positive", label: "In profit" }, { value: "negative", label: "At a loss" }]} /></div>
        <div className="w-40"><Select aria-label="Sale status" value={f.sale} onChange={(v) => set({ sale: v })} allLabel="Any sale status"
          options={[{ value: "active", label: "Marked for sale" }, { value: "ready", label: "Ready to list" }, { value: "listed", label: "Listed" },
            { value: "reserved", label: "Reserved" }, { value: "withdrawn", label: "Withdrawn" }, { value: "none", label: "Not for sale" }]} /></div>
        <div className="w-32"><Select aria-label="Photos" value={f.has_photos} onChange={(v) => set({ has_photos: v })} allLabel="Any photos"
          options={[{ value: "true", label: "Has photos" }, { value: "false", label: "No photos" }]} /></div>
        <div className="w-36"><Select aria-label="Platform" value={f.platform} onChange={(v) => set({ platform: v })} allLabel="Any platform"
          options={opts(facets?.platforms, ["vinted", "cardmarket", "ebay", "marktplaats", "other"], (v) => PLATFORM_LABEL[v as Platform] ?? v)} /></div>
        <div className="flex items-center gap-1" role="group" aria-label="Price per copy">
          <div className="w-24"><Input aria-label="Min price per copy" type="number" min="0" step="0.01" placeholder="Min €" value={f.price_min} onChange={(e) => set({ price_min: e.target.value })} /></div>
          <span className="text-muted">–</span>
          <div className="w-24"><Input aria-label="Max price per copy" type="number" min="0" step="0.01" placeholder="Max €" value={f.price_max} onChange={(e) => set({ price_max: e.target.value })} /></div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Checkbox label="Needs price" checked={f.needs_price === "true"} onChange={(e) => set({ needs_price: e.target.checked ? "true" : "" })} />
        <Checkbox label="Price stale" checked={f.stale === "true"} onChange={(e) => set({ stale: e.target.checked ? "true" : "" })} />
        <Checkbox label="No cost" checked={f.cost_missing === "true"} onChange={(e) => set({ cost_missing: e.target.checked ? "true" : "" })} />
        <div className="ml-auto flex items-center gap-2">
          <div className="w-44"><Select aria-label="Sort by" value={f.sort} onChange={(v) => set({ sort: v, order: "" })} options={SORT_OPTIONS} /></div>
          <SegmentedControl label="Sort direction" value={dir} onChange={onDir} options={[{ value: "desc", label: "↓" }, { value: "asc", label: "↑" }]} />
          {dirty && <Button variant="ghost" size="sm" onClick={clear}>Clear filters</Button>}
        </div>
      </div>
    </div>);
}
