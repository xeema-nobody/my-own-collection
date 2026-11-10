"""Read a graded-card slab from a photo: is it a slab, and what does the label say.

Slab cases sit inside bags and reflect light, so finding the case as a rectangle is unreliable (measured on 24 real
photos: the quad came out loose or missing). The label is found by its text instead:
  1. the upper part of the photo is read in overlapping tiles (labels are small in a phone photo, tesseract needs
     the text about 30 px tall, and one tile may cut the label in half),
  2. a tier word (MINT, GEM MINT, PRISTINE) marks the label; a cert-length digit run confirms it,
  3. the grade glyph is the largest text near the tier word, so that spot is read again, digits only,
  4. `slabfields.parse_label` votes grader / cert / tier over all the lines (pure, unit-tested).
A photo with no tier word and no cert is not a slab and costs only step 1.

Locate, then read (slices 5 + 6): the slab box is found first, then the label as the first dense text band below the
top of the slab (`locate_label`). Only that crop is read: ~8 tesseract calls instead of ~29 (psm 11 + 6 over the
crop, a digits-only read of the cert corner below the tier word, tight grade-glyph crops beside it). The tile
reader below stays as the fallback when no label band is found or the crop is not a label.

Position first: the slab is the one big non-background blob (`find_slab`), and the label always sits in the top third
of it, with the grade glyph beside the tier word. So the photo is cropped to the slab, the label zone is blown up to a fixed
width (text size no longer depends on how far away the phone was) and the grade is read from tight crops next to the tier word. If no slab blob is found the old whole-photo tile search runs unchanged."""
import asyncio
import re
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageOps

from app.providers.ocr import tesseract as T
from app.providers.ocr.slabfields import GRADE_RE, SlabLabel, parse_label, plausible

TILE_W, TILE_H, SCALE = 0.5, 0.32, 1.6
TILE_X = (0.0, 0.25, 0.5)
TILE_Y = (0.04, 0.16, 0.28)
TIER_WORD = re.compile(r"^(MINT|PRISTINE|NM-?MT)\W*$", re.I)
ZONE_H = 0.34  # label zone: top share of the slab's height
ZONE_W = 2000  # zone is scaled to this width before reading
ZONE_TILES = ((0.0, 0.0), (0.3, 0.0), (0.5, 0.0), (0.0, 0.4), (0.3, 0.4), (0.5, 0.4))  # (x, y) shares, tile 0.5 x 0.6
GLYPH_PSMS = (8, 7)
GRADE_BOX = (5.0, 6.0, 3.0)  # crop around the tier word: widths left+right, heights above, heights below


@dataclass
class SlabRead:
    label: SlabLabel
    lines: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.label.as_dict()


def find_slab(img: Image.Image) -> tuple[int, int, int, int] | None:
    """Box of the slab as the biggest blob lighter than the background (a slab is clear plastic on a dark table).
    The background level is taken from the photo's border. None when there is no such blob."""
    k = 500 / max(img.size)
    g = np.asarray(img.convert("L").resize((max(1, round(img.width * k)), max(1, round(img.height * k)))))
    g = cv2.GaussianBlur(g, (7, 7), 0)
    h, w = g.shape
    border = np.concatenate([g[:8].ravel(), g[-8:].ravel(), g[:, :8].ravel(), g[:, -8:].ravel()])
    mask = (g > float(np.median(border)) + 25).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15)))
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.08 * w * h:
        return None
    x, y, bw, bh = cv2.boundingRect(c)
    if bh < bw:  # a slab stands upright in the photo
        return None
    return tuple(int(v / k) for v in (x, y, x + bw, y + bh))  # type: ignore[return-value]


LABEL_W = 1800  # label crop is scaled to this width before reading
LABEL_MAX_TOP = 0.22  # the label starts within this share of the slab's height
# cert corner reads (x share, y share of the label crop, width after scaling, psm): digits only, bottom right of the label
CERT_CORNERS = ((0.55, 0.40, 1000, 11), (0.45, 0.35, 1100, 6))
RIGHT_HALF = (0.45, 1.4)  # x share where the right half starts, scale: tesseract reads a tile better than a whole label


def locate_label(img: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    """Box of the label inside the slab box: the first band of dense vertical strokes (text) in the top part of the
    slab, rows measured on the central columns. The label is a text-rich strip, the plastic above it is quiet and
    the card art under it starts a few percent lower. None when no band starts in the top share of the slab."""
    x0, y0, x1, y1 = box
    sw, sh = x1 - x0, y1 - y0
    if sw < 100 or sh < 150:
        return None
    c = img.crop((x0 + int(sw * 0.12), y0, x1 - int(sw * 0.12), y0 + int(sh * 0.42))).convert("L")
    k = 500 / c.width
    g = cv2.GaussianBlur(np.asarray(c.resize((500, max(1, round(c.height * k))))), (3, 3), 0)
    edges = (np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)) > 80).astype(np.float32)
    prof = cv2.blur(edges.sum(1).reshape(-1, 1), (1, 5)).ravel()
    on = prof > max(6.0, 0.25 * float(np.percentile(prof, 90)))
    min_h, max_gap, n, i = 0.07 * sh * k, 0.02 * sh * k, len(on), 0
    while i < n:
        if not on[i]:
            i += 1
            continue
        j, gap = i, 0
        while j < n and (on[j] or gap < max_gap):  # a short quiet gap (between label lines) does not end the band
            gap = 0 if on[j] else gap + 1
            j += 1
        j -= gap
        if j - i >= min_h:
            top, bottom = y0 + int(i / k), y0 + int(j / k)
            if top - y0 > LABEL_MAX_TOP * sh:
                return None
            pad = int(0.01 * sh)
            return (x0 + int(sw * 0.04), max(y0, top - pad), x1 - int(sw * 0.04), bottom + pad)
        i = j
    return None


def label_tilt(c: Image.Image, lim: float = 12.0, step: float = 0.5) -> float:
    """Tilt of the label's text lines in degrees: the rotation that makes the rows of ink sharpest (row sums vary
    most when lines are level). A phone photo of a slab is rarely level, and tesseract returns garbage on text
    tilted by more than ~4 degrees (IMG_3019: 8.5 degrees, nothing read; level, everything read)."""
    g = np.asarray(c.convert("L").resize((600, max(1, round(c.height * 600 / c.width)))))
    ink = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 12)
    h, w = ink.shape
    best, best_a = -1.0, 0.0
    for a in np.arange(-lim, lim + step, step):
        r = cv2.warpAffine(ink, cv2.getRotationMatrix2D((w / 2, h / 2), float(a), 1.0), (w, h))
        v = float(np.var(r.sum(1) / 255.0))
        if v > best:
            best, best_a = v, float(a)
    return best_a


def _label_crop(img: Image.Image, lb: tuple[int, int, int, int], deskew: bool = False) -> Image.Image:
    pad = round((lb[3] - lb[1]) * 0.15)
    c = img.crop((lb[0], max(0, lb[1] - pad), lb[2], min(img.height, lb[3] + pad)))
    c = ImageOps.autocontrast(c.resize((LABEL_W, max(1, round(c.height * LABEL_W / c.width))), Image.LANCZOS), cutoff=1)
    a = label_tilt(c) if deskew else 0.0
    if abs(a) >= 1.0:
        edge = np.asarray(c.convert("L"))
        fill = int(np.median(np.concatenate([edge[:4].ravel(), edge[-4:].ravel()])))
        c = c.rotate(a, resample=Image.BICUBIC, fillcolor=(fill,) * 3 if c.mode == "RGB" else fill)
    return c


async def _cert_lines(label: Image.Image) -> list[str]:
    """Digit-only reads of the corner where every grader prints the cert (right, lower half of the label)."""
    async def one(x0: float, y0: float, w: int, psm: int) -> list[str]:
        c = label.crop((int(label.width * x0), int(label.height * y0), label.width, label.height))
        c = ImageOps.expand(c.resize((w, max(1, round(c.height * w / c.width))), Image.LANCZOS), 20, fill=255)
        return _group([x for x in await T._run_words(c, psm, "0123456789") if x[1] >= 20])
    return [ln for got in await asyncio.gather(*[one(*v) for v in CERT_CORNERS]) for ln in got]


# (x share where the grade column starts, psms): every grader prints the grade right; the label is tilted in a phone
# photo, so one cut clips a glyph the other keeps (0.70 reads BGS 9.5 whole, 0.62 reads a lone PSA 9). Reads are pooled.
GRADE_COLUMNS = ((0.70, (11, 6)), (0.62, (11, 6, 7)))
GRADE_COL_W = 700  # width after scaling


async def _grade_column(label: Image.Image) -> list[tuple[float, int]]:
    """Grade tokens (value, glyph height) from the label's right column, digits only. The grade is the biggest
    number there (ACE, Beckett: above the tier word; PSA: below it); the cert is too long to look like a grade."""
    async def one(x0: float, psm: int) -> list[tuple[float, int]]:
        c = label.crop((int(label.width * x0), 0, label.width, label.height)).convert("L")
        k = GRADE_COL_W / c.width
        c = ImageOps.expand(c.resize((GRADE_COL_W, max(1, round(c.height * k))), Image.LANCZOS), 20, fill=255)
        out = []
        for text, conf, _, _, _, h in await T._run_words(c, psm, "0123456789."):
            m = GRADE_RE.fullmatch(text)
            if m and conf >= 40:
                out.append((float(m.group(1)), round(h / k)))
        return out
    got = await asyncio.gather(*[one(x0, psm) for x0, psms in GRADE_COLUMNS for psm in psms])
    return [g for gs in got for g in gs]


async def _read_label_crop(img: Image.Image, lb: tuple[int, int, int, int], deskew: bool = False) -> SlabRead | None:
    label = await asyncio.to_thread(_label_crop, img, lb, deskew)
    x0, sc = RIGHT_HALF
    right = label.crop((int(label.width * x0), 0, label.width, label.height))
    right = right.resize((round(right.width * sc), round(right.height * sc)), Image.LANCZOS)
    reads, cert_lines = await asyncio.gather(
        asyncio.gather(T._run_words(label, 11), T._run_words(label, 6), T._run_words(right, 6)), _cert_lines(label))
    lines, anchors = [], []
    for k, words in enumerate(reads):
        words = [w for w in words if w[1] >= 30]
        lines += _group(words)
        if k < 2:  # anchors in label coordinates (the right-half read is scaled and shifted)
            anchors += [(w[1], w[2], w[3], w[4], w[5]) for w in words if TIER_WORD.match(w[0])]
    parsed = parse_label(lines, cert_lines)
    if not parsed.is_slab:
        return None
    grade = pick_grade(await _grade_column(label), parsed.tier)
    best = sorted(anchors, key=lambda a: -a[0])[:1]
    if grade is not None:
        parsed.grade = grade
    elif best:
        found = [g for gs in await asyncio.gather(*[_grade_glyph(label, a, GLYPH_PSMS) for a in best]) for g in gs]
        grade = pick_grade(found, parsed.tier)
        if grade is not None:
            parsed.grade = grade
    return SlabRead(parsed, lines + cert_lines)


def _zone(img: Image.Image) -> Image.Image | None:
    box = find_slab(img)
    if not box:
        return None
    z = img.crop((box[0], box[1], box[2], box[1] + round((box[3] - box[1]) * ZONE_H)))
    if z.width < 200 or z.height < 60:
        return None
    return z.resize((ZONE_W, round(z.height * ZONE_W / z.width)), Image.LANCZOS)


def _tiles(img: Image.Image, grid=None, tw: float = TILE_W, th: float = TILE_H, scale: float = SCALE):
    grid = grid or [(x, y) for y in TILE_Y for x in TILE_X]
    out = []
    for x, y in grid:
        x0, y0 = int(img.width * x), int(img.height * y)
        c = img.crop((x0, y0, int(img.width * (x + tw)), int(img.height * (y + th))))
        c = c.resize((round(c.width * scale), round(c.height * scale)), Image.LANCZOS)
        out.append((ImageOps.autocontrast(c, cutoff=1), x0, y0))
    return out


def _group(words: list[tuple[str, float, int, int, int, int]]) -> list[str]:
    """Words of one tile back into text lines (tops within half a word height share a line)."""
    rows: list[list] = []
    for w in sorted(words, key=lambda w: (w[3], w[2])):
        if rows and abs(rows[-1][0][3] - w[3]) < 0.6 * max(w[5], 1):
            rows[-1].append(w)
        else:
            rows.append([w])
    return [" ".join(w[0] for w in sorted(r, key=lambda w: w[2])) for r in rows]


async def _read_tiles(img: Image.Image, grid=None, tw: float = TILE_W, th: float = TILE_H, scale: float = SCALE):
    tiles = await asyncio.to_thread(_tiles, img, grid, tw, th, scale)
    reads = await asyncio.gather(*[T._run_words(t, psm) for t, _, _ in tiles for psm in (11, 6)])
    lines, anchors = [], []
    for k, words in enumerate(reads):
        _, x0, y0 = tiles[k // 2]
        words = [w for w in words if w[1] >= 30]
        lines += _group(words)
        for text, conf, x, y, w, h in words:
            if TIER_WORD.match(text):
                anchors.append((conf, x0 + x / scale, y0 + y / scale, w / scale, h / scale))
    return lines, anchors


async def _grade_near(img: Image.Image, anchor) -> list[tuple[float, int]]:
    """Grade tokens (value, glyph height) around one tier word, digits only. The grade is the biggest text."""
    _, ax, ay, aw, ah = anchor
    side, up, down = GRADE_BOX
    box = (int(ax - side * aw), int(ay - up * ah), int(ax + aw + side * aw), int(ay + ah + down * ah))
    box = (max(box[0], 0), max(box[1], 0), min(box[2], img.width), min(box[3], img.height))
    if box[2] - box[0] < 8 or box[3] - box[1] < 8:
        return []
    crop = img.crop(box)
    k = max(1.0, 700 / max(crop.width, 1))
    crop = ImageOps.autocontrast(crop.resize((round(crop.width * k), round(crop.height * k)), Image.LANCZOS), cutoff=1)
    found: list[tuple[float, int]] = []
    for psm in (11, 6):
        for text, conf, _, _, _, h in await T._run_words(crop, psm, "0123456789."):
            m = GRADE_RE.fullmatch(text)
            if m and conf >= 40:
                found.append((float(m.group(1)), round(h / k)))
    return found


def pick_grade(found: list[tuple[float, int]], tier: str | None = None) -> float | None:
    """Largest glyphs win (the grade is bigger than subgrades, cert and card text); equal size: most reads.
    Reads the tier word does not allow (a GEM MINT 4) are dropped first."""
    # "GEM" is often lost from "GEM MINT", so a 9.5 survives a MINT tier; whole-number reads stay strict
    found = [(v, h) for v, h in found if plausible(tier, v) or (tier == "MINT" and v == 9.5)]
    if not found:
        return None
    top = max(h for _, h in found)
    near = [v for v, h in found if h >= 0.8 * top]
    near = [v for v in near if not (v == int(v) and (v + 0.5) in near)]  # a 9 beside a 9.5 is the 9.5 cut short
    return max(set(near), key=lambda v: (v == 10 or v != int(v), near.count(v)))  # 9.5 / 10 beat a lone 5 / 1 cut from them


async def _grade_glyph(zone: Image.Image, anchor, psms=(8, 10, 7)) -> list[tuple[float, int]]:
    """Grade tokens (value, glyph height) from tight crops next to one tier word: above it (ACE, BGS: the big glyph) and
    just below it (PSA: the small grade under MINT). Tight single-glyph crops read where a whole label does not."""
    _, ax, ay, aw, ah = anchor
    boxes = ((ax - 0.25 * aw, ay - 4.5 * ah, ax + 1.25 * aw, ay - 0.1 * ah),  # above, as wide as the tier word
             (ax - 1.0 * aw, ay - 4.5 * ah, ax + 1.25 * aw, ay - 0.1 * ah),  # above, room for 9.5 left of a "MINT" of "GEM MINT"
             (ax - 0.3 * aw, ay + 0.9 * ah, ax + 1.3 * aw, ay + 2.3 * ah))  # below
    found: list[tuple[float, int]] = []
    for box in boxes:
        box = (int(max(box[0], 0)), int(max(box[1], 0)), int(min(box[2], zone.width)), int(min(box[3], zone.height)))
        if box[2] - box[0] < 8 or box[3] - box[1] < 8:
            continue
        c = zone.crop(box)
        k = max(1.0, 200 / c.height)
        c = ImageOps.autocontrast(c.resize((round(c.width * k), round(c.height * k)), Image.LANCZOS).convert("L"), cutoff=1)
        c = ImageOps.expand(c, 30, fill=255)
        for psm in psms:
            for text, conf, _, _, _, h in await T._run_words(c, psm, "0123456789."):
                m = GRADE_RE.fullmatch(text)
                if m and conf >= 30:
                    found.append((float(m.group(1)), round(h / k)))
    return found


async def read_slab(img: Image.Image) -> SlabRead | None:
    """None when the photo shows no graded-card label."""
    box = await asyncio.to_thread(find_slab, img)
    lb = await asyncio.to_thread(locate_label, img, box) if box else None
    got = await _read_label_crop(img, lb) if lb else None
    if got and got.label.cert and got.label.cert_sure:  # a missing grade is no reason to look again: the cert page has it
        return got
    if lb:  # tilted text reads as garbage: level the label and read it again before the slow tile reader
        # (leveling everywhere was measured worse: it moved clean reads, ACE 9 -> "PSA 2023 1519", BGS 9.5 -> 10)
        level = await _read_label_crop(img, lb, deskew=True)
        if level and level.label.cert and level.label.cert_sure:
            return _merge(level, got)
        got = _merge(got, level)
    # no label band, nothing label-like in it, or a cert / grade the cheap read could not settle: the tile readers
    # (slower, ~6 s) look again; their sure cert / grade fills what the cheap read lacked
    slow = await _read_tiles_path(img)
    return _merge(got, slow)


def _merge(fast: SlabRead | None, slow: SlabRead | None) -> SlabRead | None:
    if not fast or not slow:
        return fast or slow
    f, s = fast.label, slow.label
    if (not f.cert or not f.cert_sure) and s.cert and (s.cert_sure or not f.cert):
        f.cert, f.cert_sure = s.cert, s.cert_sure
        f.cert_alt = tuple(dict.fromkeys(c for c in (*f.cert_alt, *s.cert_alt) if c != f.cert))[:2]
        if f.grader is None or not f.grader_seen:
            f.grader, f.grader_seen = s.grader or f.grader, s.grader_seen or f.grader_seen
    if f.grade is None:
        f.grade = s.grade
    if f.tier is None:
        f.tier = s.tier
    return SlabRead(f, fast.lines + slow.lines)


async def _read_tiles_path(img: Image.Image) -> SlabRead | None:
    zone = await asyncio.to_thread(_zone, img)
    if zone is not None:
        lines, anchors = await _read_tiles(zone, ZONE_TILES, 0.5, 0.6, 1.0)
        label = parse_label(lines)
        if label.is_slab:
            grade = None
            if anchors:
                best = sorted(anchors, key=lambda a: -a[0])[:2]
                found = [g for gs in await asyncio.gather(*[_grade_glyph(zone, a) for a in best]) for g in gs]
                grade = pick_grade(found, label.tier)
                if grade is None:
                    found = [g for gs in await asyncio.gather(*[_grade_near(zone, a) for a in best]) for g in gs]
                    grade = pick_grade(found, label.tier)
            if grade is not None:
                label.grade = grade
            return SlabRead(label, lines)
    lines, anchors = await _read_tiles(img)  # no slab blob, or nothing label-like in it: whole-photo search
    label = parse_label(lines)
    if not label.is_slab:
        return None
    if anchors:
        best = sorted(anchors, key=lambda a: -a[0])[:2]
        found = [g for grades in await asyncio.gather(*[_grade_near(img, a) for a in best]) for g in grades]
        grade = pick_grade(found, label.tier)
        if grade is not None:
            label.grade = grade
    return SlabRead(label, lines)
