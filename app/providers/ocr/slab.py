"""Read a graded-card slab from a photo: is it a slab, and what does the label say.

Slab cases sit inside bags and reflect light, so finding the case as a rectangle is unreliable (measured on 24 real
photos: the quad came out loose or missing). The label is found by its text instead:
  1. the upper part of the photo is read in overlapping tiles (labels are small in a phone photo, tesseract needs
     the text about 30 px tall, and one tile may cut the label in half),
  2. a tier word (MINT, GEM MINT, PRISTINE) marks the label; a cert-length digit run confirms it,
  3. the grade glyph is the largest text near the tier word, so that spot is read again, digits only,
  4. `slabfields.parse_label` votes grader / cert / tier over all the lines (pure, unit-tested).
A photo with no tier word and no cert is not a slab and costs only step 1.

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
    found = [(v, h) for v, h in found if plausible(tier, v)]
    if not found:
        return None
    top = max(h for _, h in found)
    near = [v for v, h in found if h >= 0.8 * top]
    return max(set(near), key=lambda v: (v == 10 or v != int(v), near.count(v)))  # 9.5 / 10 beat a lone 5 / 1 cut from them


async def _grade_glyph(zone: Image.Image, anchor) -> list[tuple[float, int]]:
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
        for psm in (8, 10, 7):
            for text, conf, _, _, _, h in await T._run_words(c, psm, "0123456789."):
                m = GRADE_RE.fullmatch(text)
                if m and conf >= 30:
                    found.append((float(m.group(1)), round(h / k)))
    return found


async def read_slab(img: Image.Image) -> SlabRead | None:
    """None when the photo shows no graded-card label."""
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
