"""Artwork matching: how well a photographed card shows the artwork of a catalog image.

SIFT features of the art box, matched with a ratio test and a RANSAC homography; the score is the inlier count.
Rotation / scale / glare tolerant, so sideways cards and sleeves are fine. Pure functions, no network."""
import io

import cv2
import numpy as np
from PIL import Image

from app.providers.ocr import cardgeom
from app.providers.ocr.tesseract import prepare

ART_BOX = (0.06, 0.10, 0.94, 0.56)  # artwork share of the card (x0, y0, x1, y1)
ART_W = 320
FLATS = 3  # flat readings of the photo tried (card, inner card, first sleeve crop)
_sift = None


def _detector():
    global _sift
    if _sift is None:
        _sift = cv2.SIFT_create(nfeatures=600)
    return _sift


def art_gray(im: Image.Image) -> np.ndarray:
    w, h = im.size
    box = (int(ART_BOX[0] * w), int(ART_BOX[1] * h), int(ART_BOX[2] * w), int(ART_BOX[3] * h))
    g = np.asarray(im.convert("L").crop(box))
    return cv2.resize(g, (ART_W, max(1, int(ART_W * g.shape[0] / g.shape[1]))))


def art_png(data: bytes) -> bytes | None:
    """Compact art crop of a catalog image (what gets cached), None when the bytes are not an image."""
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        ok, buf = cv2.imencode(".png", art_gray(im.convert("RGBA").convert("RGB")))
        return buf.tobytes() if ok else None
    except Exception:  # noqa: BLE001
        return None


def photo_arts(image: bytes) -> list[np.ndarray]:
    """Art crops of the photographed card, one per flat reading. Empty when no card is found."""
    img = prepare(image)
    quad = cardgeom.find_quad(img)
    if quad is None:
        return []
    return [art_gray(f) for f in cardgeom.flats(img, quad, ())[:FLATS]]


def inliers(a: np.ndarray, b: np.ndarray) -> int:
    det = _detector()
    ka, da = det.detectAndCompute(a, None)
    kb, db = det.detectAndCompute(b, None)
    if da is None or db is None or len(ka) < 4 or len(kb) < 4:
        return 0
    pairs = cv2.BFMatcher().knnMatch(da, db, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
    if len(good) < 4:
        return 0
    pa = np.float32([ka[g.queryIdx].pt for g in good])
    pb = np.float32([kb[g.trainIdx].pt for g in good])
    _, mask = cv2.findHomography(pa, pb, cv2.RANSAC, 6.0)
    return int(mask.sum()) if mask is not None else 0


def score(photo: list[np.ndarray], cached_png: bytes) -> int:
    ref = cv2.imdecode(np.frombuffer(cached_png, np.uint8), cv2.IMREAD_GRAYSCALE)
    if ref is None or not photo:
        return 0
    return max(inliers(p, ref) for p in photo)
