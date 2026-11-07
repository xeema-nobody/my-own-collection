"""Read a graded-card slab from a photo: is it a slab, and what does the label say.

Slab cases sit inside bags and reflect light, so finding the case as a rectangle is unreliable (measured on 24 real
photos: the quad came out loose or missing). The label is found by its text instead:
  1. the upper part of the photo is read in overlapping tiles (labels are small in a phone photo, tesseract needs
     the text about 30 px tall, and one tile may cut the label in half),
  2. a tier word (MINT, GEM MINT, PRISTINE) marks the label; a cert-length digit run confirms it,
  3. the grade glyph is the largest text near the tier word, so that spot is read again, digits only,
  4. `slabfields.parse_label` votes grader / cert / tier over all the lines (pure, unit-tested).
A photo with no tier word and no cert is not a slab and costs only step 1."""
import asyncio
import re
from dataclasses import dataclass, field

from PIL import Image, ImageOps

from app.providers.ocr import tesseract as T
from app.providers.ocr.slabfields import GRADE_RE, SlabLabel, parse_label, plausible

TILE_W, TILE_H, SCALE = 0.5, 0.32, 1.6
TILE_X = (0.0, 0.25, 0.5)
TILE_Y = (0.04, 0.16, 0.28)
TIER_WORD = re.compile(r"^(MINT|PRISTINE|NM-?MT)\W*$", re.I)
GRADE_BOX = (5.0, 6.0, 3.0)  # crop around the tier word: widths left+right, heights above, heights below


@dataclass
class SlabRead:
    label: SlabLabel
    lines: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.label.as_dict()


def _tiles(img: Image.Image) -> list[tuple[Image.Image, int, int]]:
    out = []
    for y in TILE_Y:
        for x in TILE_X:
            x0, y0 = int(img.width * x), int(img.height * y)
            c = img.crop((x0, y0, int(img.width * (x + TILE_W)), int(img.height * (y + TILE_H))))
            c = c.resize((round(c.width * SCALE), round(c.height * SCALE)), Image.LANCZOS)
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


async def _read_tiles(img: Image.Image):
    tiles = await asyncio.to_thread(_tiles, img)
    reads = await asyncio.gather(*[T._run_words(t, psm) for t, _, _ in tiles for psm in (11, 6)])
    lines, anchors = [], []
    for k, words in enumerate(reads):
        _, x0, y0 = tiles[k // 2]
        words = [w for w in words if w[1] >= 30]
        lines += _group(words)
        for text, conf, x, y, w, h in words:
            if TIER_WORD.match(text):
                anchors.append((conf, x0 + x / SCALE, y0 + y / SCALE, w / SCALE, h / SCALE))
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
    return max(set(near), key=near.count)


async def read_slab(img: Image.Image) -> SlabRead | None:
    """None when the photo shows no graded-card label."""
    lines, anchors = await _read_tiles(img)
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
