"""Local OCR through the `tesseract` binary (no network, no paid API).

A real phone photo shows the card in the middle of a table, so a fixed top crop reads table (measured on 15 real
photos: 3 of 15 hit). The card is therefore found first (it is brighter than the table: Otsu threshold on a
thumbnail, largest lit box), and the name is read from that box in stages, cheapest first, each stage returning its
lines so the caller can stop at the first confident match:
  1. top band of the card box (sparse + one-line modes), upscaled
  2. tight name strip of the card box (excludes stage label, HP and type icon)
  2b. both crops reduced to their dark pixels (names over busy art)
  3. whole card box
  4. whole image (the card could not be located)
When the live view already cropped the frame to the framing guide the card box is the whole image and the same
stages apply. Lines come back with a confidence and a vertical position."""
import asyncio
import io
import logging
from typing import AsyncIterator

from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

from app.config import settings
from app.providers.ocr.base import ImageError, OcrLine, OcrUnavailable

log = logging.getLogger(__name__)
Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard (Pillow raises above 2x this)
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_SIDE = 2400  # longest side kept for the card search and the whole-image stage
CROP_WIDTH = 1400  # name crops are scaled to this width (phone photo is wider, a guide crop may be smaller)
BAND = (0.0, 0.22)  # top share of the card box that holds name + stage + HP
STRIP = (0.03, 0.15, 0.10, 0.76)  # y0, y1, x0, x1 of the name alone (no stage label, HP, type icon)
MIN_CARD_AREA, MAX_CARD_AREA = 0.06, 0.97  # share of the photo a plausible card box covers
DARK_CUTS = (90, 60)  # luminance cuts for the binarized stages (after per-crop autocontrast)
TIMEOUT_S = 10
_slots = asyncio.Semaphore(2)  # a LAN-reachable endpoint must not be able to saturate the CPU


def prepare(data: bytes) -> Image.Image:
    """Decode, fix orientation, grayscale; long side capped at MAX_SIDE. Contrast is normalised per crop."""
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ALLOWED_FORMATS:
            raise ImageError("unsupported image type (use JPEG, PNG or WebP)")
        img = ImageOps.exif_transpose(img)
        img.load()
    except ImageError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as e:
        raise ImageError("not a readable image") from e
    img = img.convert("L")
    if max(img.size) > MAX_SIDE:
        k = MAX_SIDE / max(img.size)
        img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
    return img


def _otsu(hist: list[int]) -> int:
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    best, best_t, w0, sum0 = -1.0, 128, 0, 0
    for t, h in enumerate(hist):
        w0 += h
        if not w0 or w0 == total:
            continue
        sum0 += t * h
        m0, m1 = sum0 / w0, (sum_all - sum0) / (total - w0)
        var = w0 * (total - w0) * (m0 - m1) ** 2
        if var > best:
            best, best_t = var, t
    return best_t


def find_card(img: Image.Image) -> tuple[int, int, int, int] | None:
    """Box (x0, y0, x1, y1 in img pixels) of the lit card against a darker (or lighter) table, or None.
    Otsu threshold on a thumbnail, specks removed with a median filter, bounding box of what is left."""
    k = 240 / max(img.size)
    small = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(1.5))
    t = _otsu(small.histogram())
    mask = small.point(lambda v: 255 if v > t else 0)
    w, h = small.size
    inner = (w // 8, h // 8, w - w // 8, h - h // 8)
    n_in = (inner[2] - inner[0]) * (inner[3] - inner[1])
    lit_all = ImageStat.Stat(mask).mean[0] * w * h
    lit_in = ImageStat.Stat(mask.crop(inner)).mean[0] * n_in
    if (lit_all - lit_in) / 255 > 0.5 * (w * h - n_in):
        mask = mask.point(lambda v: 255 - v)  # the frame edge is the lit part: the table is light, card darker
    mask = mask.filter(ImageFilter.MedianFilter(7))
    box = mask.getbbox()
    if not box:
        return None
    area = (box[2] - box[0]) * (box[3] - box[1]) / (small.width * small.height)
    if not MIN_CARD_AREA <= area <= MAX_CARD_AREA:
        return None
    return (round(box[0] / k), round(box[1] / k), round(box[2] / k), round(box[3] / k))


def _dark(img: Image.Image, cut: int) -> Image.Image:
    return img.point(lambda v: 255 if v > cut else 0)


def crop_rel(img: Image.Image, box: tuple[int, int, int, int], y0: float, y1: float,
             x0: float = 0.0, x1: float = 1.0) -> Image.Image:
    """Crop given as shares of `box`, scaled to CROP_WIDTH, contrast normalised on the crop alone."""
    bw, bh = box[2] - box[0], box[3] - box[1]
    c = img.crop((box[0] + round(bw * x0), box[1] + round(bh * y0), box[0] + round(bw * x1), box[1] + round(bh * y1)))
    if c.width < 2 or c.height < 2:
        return c
    c = c.resize((CROP_WIDTH, max(1, round(c.height * CROP_WIDTH / c.width))), Image.LANCZOS)
    return ImageOps.autocontrast(c, cutoff=1)


def parse_tsv(tsv: str, height: int) -> list[OcrLine]:
    """Group tesseract TSV words into lines: mean confidence, text, vertical position."""
    lines: dict[tuple, dict] = {}
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12 or c[0] != "5":
            continue
        text, conf = c[11].strip(), float(c[10])
        if not text or conf < 0:
            continue
        ln = lines.setdefault(tuple(c[2:5]), {"w": [], "conf": [], "top": float(c[7])})
        ln["w"].append(text)
        ln["conf"].append(conf)
    return [OcrLine(" ".join(v["w"]), sum(v["conf"]) / len(v["conf"]), v["top"] / max(height, 1))
            for v in lines.values()]


async def _run(img: Image.Image, psm: int) -> list[OcrLine]:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    async with _slots:
        try:
            proc = await asyncio.create_subprocess_exec(
                settings.tesseract_cmd, "stdin", "stdout", "--psm", str(psm), "-l", "eng", "tsv",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await asyncio.wait_for(proc.communicate(buf.getvalue()), TIMEOUT_S)
        except FileNotFoundError as e:
            raise OcrUnavailable("tesseract is not installed in the app image") from e
        except asyncio.TimeoutError as e:
            proc.kill()
            raise OcrUnavailable("text reader timed out") from e
    if proc.returncode != 0:
        log.warning("tesseract failed: %s", err.decode(errors="ignore")[:200])
        raise OcrUnavailable("text reader failed")
    return parse_tsv(out.decode(errors="ignore"), img.height)


class TesseractOcr:
    async def stages(self, image: bytes) -> AsyncIterator[list[OcrLine]]:
        """Lines per stage, cheapest first. The caller stops at the first stage that matches a card name."""
        img = await asyncio.to_thread(prepare, image)
        box = await asyncio.to_thread(find_card, img) or (0, 0, img.width, img.height)
        located = box != (0, 0, img.width, img.height)
        band = await asyncio.to_thread(crop_rel, img, box, *BAND)
        yield await _run(band, 11) + await _run(band, 7)
        y0, y1, x0, x1 = STRIP
        strip = await asyncio.to_thread(crop_rel, img, box, y0, y1, x0, x1)
        yield await _run(strip, 7)
        for t in DARK_CUTS:  # name on busy art: keep only the dark glyph pixels
            yield await _run(await asyncio.to_thread(_dark, band, t), 11) + await _run(
                await asyncio.to_thread(_dark, strip, t), 11)
        card = await asyncio.to_thread(crop_rel, img, box, 0.0, 1.0)
        yield await _run(card, 11)
        if located:
            yield await _run(await asyncio.to_thread(crop_rel, img, (0, 0, img.width, img.height), 0.0, 1.0), 11)

    async def read_lines(self, image: bytes) -> list[OcrLine]:
        return [ln async for lines in self.stages(image) for ln in lines]
