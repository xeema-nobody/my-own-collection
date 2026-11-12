import { Badge } from "../ui";
import { money } from "../../lib/api";

/** Why a value is not an exact-grade price; "" = exact. */
export function whyEstimated(i: any): string {
  const why = [] as string[];
  if (i.match === "bucket") why.push(`company-agnostic ${i.grade_key_used} price, not ${i.grading?.company} ${i.grading?.grade}`);
  else if (i.match === "lower") why.push(`no ${i.grading?.company} ${i.grading?.grade} price, using lower grade ${i.grade_key_used}`);
  else if (i.match === "needs_graded_price") why.push("no graded price yet, not counted");
  if (i.estimated && i.match === "exact") why.push("variant price missing, used another variant");
  return why.join("; ");
}

export const KIND_TONE = { sold: "ok", market: "neutral", ask: "warn" } as const;

export function Value({ i }: { i: any }) {
  if (i.needs_price) return <Badge tone="warn" title="A slab is not worth its raw copy, so it is left out of totals until a graded price is fetched">needs price</Badge>;
  if (i.value == null) return <span className="text-muted" title="No price for this grade">no price</span>;
  const why = whyEstimated(i);
  return <span className="inline-flex items-center justify-end gap-1.5" title={i.headline_rule ?? ""}>
    {why && <span title={why} className="text-warn">≈</span>}<span className="font-semibold">{money(i.value)}</span>
    <Badge tone={KIND_TONE[i.price_kind as keyof typeof KIND_TONE] ?? "neutral"}>{i.price_kind}</Badge></span>;
}

export const detail = (i: any) => i.card?.kind === "sealed" ? `${i.language.toUpperCase()} · Sealed` : `${i.variant ? `${i.variant} · ` : ""}${i.language.toUpperCase()} · ${i.grading ? `${i.grading.company} ${i.grading.grade}` : i.condition}`;
