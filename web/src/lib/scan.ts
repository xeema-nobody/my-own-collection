// Phone scanning helpers: error wording, photo cropping, remembered choices. No network here (api.ts does that).
import { ApiError, type Acquired } from "./api";

/** Plain-words reason for a failed scan call, aimed at someone standing with a card in one hand. */
export function friendlyScanError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 403) return "Your computer refused this phone. Check that Tailscale is signed in with the same account as the computer.";
    if (e.status === 413) return "That photo is too big. Try again a bit further from the card.";
    if (e.status === 400) return "Couldn't use that photo. Try again.";
    if (e.status === 503) return "The text reader on your computer isn't working. You can still type the card name.";
    if (e.status >= 500) return "Your computer had a problem. Try again, or type the card name.";
    return e.message;
  }
  // fetch() rejects with a TypeError when nothing answers
  return "Can't reach your computer. Check that Tailscale is on (on the phone and the computer) and that the computer is awake.";
}

export type Rect = { sx: number; sy: number; sw: number; sh: number };
export const CARD_RATIO = 63 / 88;

/** The framing guide in source pixels: a card-shaped box centred in the frame, `fill` of the limiting side. */
export function guideRect(w: number, h: number, fill = 0.82): Rect {
  let sw = w * fill, sh = sw / CARD_RATIO;
  if (sh > h * fill) { sh = h * fill; sw = sh * CARD_RATIO; }
  return { sx: Math.round((w - sw) / 2), sy: Math.round((h - sh) / 2), sw: Math.round(sw), sh: Math.round(sh) };
}

export function fitWidth(sw: number, sh: number, maxW: number): { w: number; h: number } {
  const k = Math.min(1, maxW / sw);
  return { w: Math.round(sw * k), h: Math.round(sh * k) };
}

function toBlob(c: HTMLCanvasElement): Promise<Blob> {
  return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error("could not encode photo"))), "image/jpeg", 0.85));
}

/** Crop `rect` out of a video frame / bitmap and downscale to at most `maxW` wide JPEG. */
export async function cropToJpeg(src: CanvasImageSource, rect: Rect, maxW = 1000): Promise<Blob> {
  const { w, h } = fitWidth(rect.sw, rect.sh, maxW);
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  c.getContext("2d")!.drawImage(src, rect.sx, rect.sy, rect.sw, rect.sh, 0, 0, w, h);
  return toBlob(c);
}

/** A photo picked with the native camera: downscale only (the card may be anywhere in it). */
export async function resizePhoto(file: Blob, maxSide = 1600): Promise<Blob> {
  const bmp = await createImageBitmap(file); // honours EXIF orientation
  const k = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
  const c = document.createElement("canvas");
  c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
  c.getContext("2d")!.drawImage(bmp, 0, 0, c.width, c.height);
  bmp.close?.();
  return toBlob(c);
}

export const CONDITIONS = ["NM", "LP", "MP", "HP", "DMG"] as const;
export const CONDITION_HELP: Record<string, string> = {
  NM: "Near mint: clean, no visible wear.", LP: "Lightly played: faint edge wear or tiny scratches.",
  MP: "Moderately played: clear wear, whitening, light creases.", HP: "Heavily played: heavy wear, creases, scuffs.",
  DMG: "Damaged: tears, bends, water damage.",
};

export type Choice = { condition: string; language: string; acquired: Acquired | null };
const KEY = "scan.choice";
const DEFAULT: Choice = { condition: "NM", language: "en", acquired: null };

export function loadChoice(): Choice {
  try {
    const c = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (c && CONDITIONS.includes(c.condition) && typeof c.language === "string") return { ...DEFAULT, ...c };
  } catch { /* private mode or bad json */ }
  return DEFAULT;
}
export function saveChoice(c: Choice) {
  try { localStorage.setItem(KEY, JSON.stringify(c)); } catch { /* ignore */ }
}

export const LANGUAGES = [["en", "English"], ["ja", "Japanese"], ["de", "German"], ["fr", "French"], ["it", "Italian"], ["es", "Spanish"], ["pt", "Portuguese"], ["ko", "Korean"], ["zh", "Chinese"]] as const;
