// One colour per price source, used consistently across charts.
export const SOURCE_COLOR: Record<string, string> = { cardmarket: "#0ea5e9", cardmarket_web: "#38bdf8", tcgplayer: "#f59e0b", pricecharting: "#10b981", altxyz: "#a855f7", manual: "#ef4444" };
export const KIND_LABEL: Record<string, string> = { sold: "sold", market: "market", ask: "ask" };
export const KIND_CLASS: Record<string, string> = {
  sold: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200",
  market: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200",
  ask: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
};
