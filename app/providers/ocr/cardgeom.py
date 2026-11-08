"""Find a trading card in a photo as a quadrilateral with the fixed 63:88 proportion and warp it flat.

Works at any position, size and tilt, on dark or light tables. Candidates come from two sources (edge contours and
brightness-mask contours), each reduced to a four-corner polygon, then scored by how well the rectified shape fits
63:88. A sleeve or toploader (outer border bigger than the card) cannot be told from the card's own inner art frame
by shape alone, so the outer quad is returned and `warp(inset=...)` can shrink it for a second read. A card that is cut off by the photo frame returns None so the caller falls back to the
older brightness stages."""
import cv2
import numpy as np
from PIL import Image

CARD_W, CARD_H = 630, 880  # flat card size (63:88 x 10)
RATIO = 63 / 88
RATIO_TOL = 0.16  # relative aspect error accepted (tilt and lens distortion)
WORK = 700  # longest side used for detection
MIN_AREA, MAX_AREA = 0.06, 0.98  # share of the photo
EDGE_MARGIN = 0.012  # corner closer than this to the frame counts as touching it


def _order(pts: np.ndarray) -> np.ndarray:
    """Corners as top-left, top-right, bottom-right, bottom-left."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s, d = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def _aspect_error(q: np.ndarray, ratio: float = RATIO) -> float:
    """Relative distance of the quad's side ratio from `ratio` (default 63:88, either orientation)."""
    w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    if min(w, h) < 1:
        return 9.0
    return abs(min(w, h) / max(w, h) - ratio) / ratio


def _quad_from(contour: np.ndarray) -> np.ndarray | None:
    hull = cv2.convexHull(contour)
    peri = cv2.arcLength(hull, True)
    approx = None
    for eps in (0.02, 0.03, 0.045, 0.06):  # loosen until the outline collapses to its four real corners
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) <= 4:
            break
    if len(approx) == 4:
        return _order(approx)
    if len(approx) < 4:
        return None
    # Still more than four points: the rotated bounding rectangle is a stand-in for the card.
    return _order(cv2.boxPoints(cv2.minAreaRect(hull)))


def _contours(gray: np.ndarray) -> list[np.ndarray]:
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    med = float(np.median(blur))
    edges = cv2.Canny(blur, max(10, 0.66 * med), min(250, 1.33 * med + 20))
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    out = list(cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0])
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    for m in (mask, 255 - mask):  # card lighter, or darker, than the table
        m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k)
        out += list(cv2.findContours(m, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0])
    return out


def _touching(q: np.ndarray, w: int, h: int) -> int:
    mx, my = EDGE_MARGIN * w, EDGE_MARGIN * h
    return sum(1 for x, y in q if x <= mx or y <= my or x >= w - 1 - mx or y >= h - 1 - my)


def find_quad(img: Image.Image, ratio: float = RATIO, tol: float = RATIO_TOL) -> np.ndarray | None:
    """Corners (tl, tr, br, bl, in img pixels) of the card, or None when no card-shaped quad is found.
    `ratio` / `tol` let the same search find a slab case (see providers/ocr/slab.py)."""
    gray = np.asarray(img.convert("L"))
    s = WORK / max(gray.shape)
    small = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else gray
    s = small.shape[1] / gray.shape[1]
    h, w = small.shape
    total = float(w * h)
    cands: list[tuple[np.ndarray, float, float]] = []  # quad, area share, aspect error
    for c in _contours(small):
        if cv2.contourArea(c) < MIN_AREA * total * 0.5:
            continue
        q = _quad_from(c)
        if q is None:
            continue
        area = cv2.contourArea(q)
        share = area / total
        err = _aspect_error(q, ratio)
        hull_fill = cv2.contourArea(cv2.convexHull(c)) / max(area, 1.0)
        if not MIN_AREA <= share <= MAX_AREA or err > tol or hull_fill < 0.8 or hull_fill > 1.25:
            continue
        if _touching(q, w, h) >= 2:  # cut off by the frame
            continue
        cands.append((q, share, err))
    if not cands:
        return None
    best = max(cands, key=lambda t: t[1] * (1 - t[2]))
    return best[0] / s


def warp(img: Image.Image, quad: np.ndarray, inset: float = 0.0) -> Image.Image:
    """Flatten the quad to CARD_W x CARD_H, long side vertical. `inset` shrinks the quad toward its centre first
    (share of its size, for a sleeve or toploader border)."""
    q = _order(quad)
    if inset:
        c = q.mean(axis=0)
        q = c + (q - c) * (1 - 2 * inset)
    w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    if w > h:  # photographed sideways: turn so the long side is vertical
        q = np.roll(q, -1, axis=0)
    dst = np.array([[0, 0], [CARD_W - 1, 0], [CARD_W - 1, CARD_H - 1], [0, CARD_H - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(q, dst)
    arr = np.asarray(img)
    flat = cv2.warpPerspective(arr, m, (CARD_W, CARD_H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(flat)


def flats(img: Image.Image, quad: np.ndarray, insets: tuple[float, ...] = (0.05, 0.10)) -> list[Image.Image]:
    """Flat readings of one found quad, best guess first. A sleeve / toploader makes the quad bigger than the card
    (border, tab): add the inner card quad found inside the flat sleeve, then insets as a fallback."""
    out = [warp(img, quad)]
    try:
        inner = find_quad(out[0])
    except Exception:  # noqa: BLE001 - geometry must never break scanning
        inner = None
    if inner is not None:
        out.append(warp(out[0], inner))
    out += sleeve_crops(out[0])
    out += [warp(img, quad, inset) for inset in insets]
    return out


# Where the card sits inside the flat sleeve / toploader (shares x0, y0, x1, y1), measured on Vault-X sleeves. The inner
# quad search is flaky there (glare, the card's own art frame); a fixed box, also shifted up and down because the card
# sits at different heights in the sleeve, is enough to read the number line.
SLEEVE_BOX = (0.10, 0.155, 0.895, 0.915)
SLEEVE_SHIFTS = (0.0, -0.075, 0.03)


SCAN = 4  # detection runs on the flat shrunk by this factor
SIZES = np.arange(0.74, 0.87, 0.02)  # card width as a share of the sleeve flat width
BORDER = 2  # border band thickness in scan pixels
SIZE_PRIOR = 4.0  # inner art frames sit inside the card and have strong edges: lean toward the larger box


def locate_card(flat: Image.Image) -> tuple[int, int, int, int] | None:
    """Card box (x0, y0, x1, y1 in flat pixels) inside a flat sleeve / toploader: the 63:88 rectangle whose four
    sides sit on the strongest edges (card edge against the sleeve), searched over size and position with integral
    images. None when no box clearly beats the average one."""
    g = np.asarray(flat.convert("L"), dtype=np.float32)
    g = cv2.GaussianBlur(cv2.resize(g, (g.shape[1] // SCAN, g.shape[0] // SCAN), interpolation=cv2.INTER_AREA), (3, 3), 0)
    H, W = g.shape
    gx = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3))  # vertical edges: left and right sides
    gy = np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))  # horizontal edges: top and bottom sides
    gx, gy = np.minimum(gx, np.percentile(gx, 99)), np.minimum(gy, np.percentile(gy, 99))  # glare streaks do not win
    ix = np.pad(gx.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    iy = np.pad(gy.cumsum(0).cumsum(1), ((1, 0), (1, 0)))

    def box_sum(i: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> float:
        return float(i[y1, x1] - i[y0, x1] - i[y1, x0] + i[y0, x0])

    best, scores = None, []
    for fw in SIZES:
        bw = int(fw * W)
        bh = int(bw / RATIO)
        if bh >= H - 2:
            continue
        for y0 in range(1, H - bh - 1, 2):
            for x0 in range(1, W - bw - 1, 2):
                x1, y1 = x0 + bw, y0 + bh
                b = BORDER
                side = (box_sum(ix, x0 - b, y0, x0 + b, y1) + box_sum(ix, x1 - b, y0, x1 + b, y1)
                        + box_sum(iy, x0, y0 - b, x1, y0 + b) + box_sum(iy, x0, y1 - b, x1, y1 + b))
                sc = side / (2 * (bw + bh) * 2 * b) * (fw / SIZES[0]) ** SIZE_PRIOR
                scores.append(sc)
                if best is None or sc > best[0]:
                    best = (sc, x0, y0, x1, y1)
    if best is None or best[0] <= 0 or best[0] < 1.4 * float(np.mean(scores)):
        return None
    _, x0, y0, x1, y1 = best
    return x0 * SCAN, y0 * SCAN, x1 * SCAN, y1 * SCAN


def sleeve_crops(flat: Image.Image) -> list[Image.Image]:
    w, h = flat.size
    x0, y0, x1, y1 = SLEEVE_BOX
    out = []
    try:
        found = locate_card(flat)
    except Exception:  # noqa: BLE001 - geometry must never break scanning
        found = None
    if found is not None:
        out.append(flat.crop(found).resize((CARD_W, CARD_H), Image.LANCZOS))
    for dy in SLEEVE_SHIFTS:
        box = (int(x0 * w), int((y0 + dy) * h), int(x1 * w), int((y1 + dy) * h))
        out.append(flat.crop(box).resize((CARD_W, CARD_H), Image.LANCZOS))
    return out


def upside_down(flat: Image.Image) -> Image.Image:
    """The same flat card turned 180 degrees (a card held sideways can be warped either way up)."""
    return flat.rotate(180)
