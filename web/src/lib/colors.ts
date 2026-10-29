// One colour per price source, from the `--src-*` tokens in index.css (theme aware).
const SOURCES = ["tcgplayer", "cardmarket", "cardmarket_web", "pricecharting", "altxyz", "manual"] as const;
export const SOURCE_COLOR: Record<string, string> = Object.fromEntries(SOURCES.map((s) => [s, `rgb(var(--src-${s}))`]));
export const SOURCE_LABEL: Record<string, string> = {
  tcgplayer: "TCGplayer", cardmarket: "Cardmarket", cardmarket_web: "Cardmarket (web)", pricecharting: "PriceCharting", altxyz: "alt.xyz", manual: "Manual",
};
export const sourceLabel = (s: string) => SOURCE_LABEL[s] ?? s;
export const KIND_TONE = { sold: "ok", market: "neutral", ask: "warn" } as const;
export const kindTone = (k: string) => (KIND_TONE as Record<string, "ok" | "neutral" | "warn">)[k] ?? "neutral";
