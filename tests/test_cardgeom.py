"""Card rectangle detection + perspective warp on synthetic photos (no real photos, no network)."""
import cv2
import numpy as np
import pytest
from PIL import Image

from app.providers.ocr import cardgeom

W, H = 1200, 1600


def card_img(w=315, h=440) -> np.ndarray:
    """A 63:88 card: yellow border, art block, text bars (a name band on top, number line at the bottom)."""
    c = np.full((h, w, 3), (30, 200, 230), np.uint8)
    cv2.rectangle(c, (12, 12), (w - 13, h - 13), (90, 60, 40), 3)
    cv2.rectangle(c, (30, 70), (w - 31, h // 2 + 20), (200, 120, 60), -1)
    cv2.rectangle(c, (30, 22), (w // 2, 50), (20, 20, 20), -1)
    cv2.rectangle(c, (30, h - 45), (w // 3, h - 25), (20, 20, 20), -1)
    return c


def photo(table, quad, card=None, sleeve=0.0, glare=False, noise=False) -> np.ndarray:
    """Card pasted on a table colour through a perspective transform onto `quad` (tl, tr, br, bl)."""
    bg = np.full((H, W, 3), table, np.uint8)
    if noise:
        bg = np.clip(bg.astype(int) + np.random.default_rng(1).integers(-25, 25, bg.shape), 0, 255).astype(np.uint8)
    card = card_img() if card is None else card
    if sleeve:
        pad = int(card.shape[1] * sleeve)
        card = cv2.copyMakeBorder(card, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(245, 245, 245))
        cv2.rectangle(card, (1, 1), (card.shape[1] - 2, card.shape[0] - 2), (60, 60, 60), 2)
    h, w = card.shape[:2]
    src = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.float32)
    m = cv2.getPerspectiveTransform(src, np.array(quad, np.float32))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (W, H))
    out = cv2.warpPerspective(card, m, (W, H))
    img = np.where(mask[..., None] > 0, out, bg)
    if glare:
        blob = np.zeros((H, W), np.uint8)
        cv2.circle(blob, tuple(int(v) for v in np.mean(quad, axis=0)), 90, 255, -1)
        img = np.where(blob[..., None] > 0, 245, img).astype(np.uint8)
    return img


def rot_quad(cx, cy, w, h, deg):
    a = np.deg2rad(deg)
    r = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    pts = np.array([[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]])
    return (pts @ r.T + [cx, cy]).tolist()


def err(found, quad):
    """Mean corner distance (px) between detected and true quad, matching corners in order."""
    return float(np.mean(np.linalg.norm(cardgeom._order(found) - cardgeom._order(np.array(quad)), axis=1)))


DARK, LIGHT, WOOD = (25, 25, 25), (235, 235, 230), (70, 110, 150)


@pytest.mark.parametrize("table", [DARK, LIGHT, WOOD])
@pytest.mark.parametrize("deg", [0, 15, -30])
def test_finds_tilted_card_on_any_table(table, deg):
    quad = rot_quad(600, 800, 560, 782, deg)
    found = cardgeom.find_quad(Image.fromarray(photo(table, quad)))
    assert found is not None
    assert err(found, quad) < 12


def test_small_card_noisy_table():
    quad = rot_quad(500, 900, 330, 461, 8)
    found = cardgeom.find_quad(Image.fromarray(photo(WOOD, quad, noise=True)))
    assert found is not None and err(found, quad) < 12


def test_perspective_skew():
    quad = [[260, 200], [900, 260], [980, 1250], [200, 1300]]
    found = cardgeom.find_quad(Image.fromarray(photo(LIGHT, quad)))
    assert found is not None and err(found, quad) < 20


def test_sleeve_finds_outer_and_inset_warp_trims_it():
    outer = rot_quad(600, 800, 520 * 1.1, 726 * 1.1, 5)
    img = Image.fromarray(photo(LIGHT, outer, sleeve=0.05))
    found = cardgeom.find_quad(img)
    assert found is not None and err(found, outer) < 20
    flat = np.asarray(cardgeom.warp(img, found, inset=0.045).convert("L"))
    assert flat[5:15, 5:-5].mean() < 200  # trimmed: no bright sleeve strip left along the top edge


def test_glare_blob_over_card():
    quad = rot_quad(600, 800, 560, 782, 10)
    found = cardgeom.find_quad(Image.fromarray(photo(DARK, quad, glare=True)))
    assert found is not None and err(found, quad) < 25


def test_cut_off_card_gives_none():
    quad = rot_quad(600, 1250, 700, 978, 0)  # runs past the bottom edge
    assert cardgeom.find_quad(Image.fromarray(photo(DARK, quad))) is None


def test_blank_and_non_card_shapes_give_none():
    assert cardgeom.find_quad(Image.new("RGB", (800, 600), (120, 120, 120))) is None
    wide = np.full((H, W, 3), 25, np.uint8)
    cv2.rectangle(wide, (100, 500), (1100, 800), (230, 230, 230), -1)  # 4:1 bar
    assert cardgeom.find_quad(Image.fromarray(wide)) is None


@pytest.mark.parametrize("deg", [0, 20, 90])
def test_warp_is_flat_and_upright(deg):
    quad = rot_quad(600, 800, 560, 782, deg)
    img = Image.fromarray(photo(LIGHT, quad))
    flat = cardgeom.warp(img, cardgeom.find_quad(img))
    assert flat.size == (cardgeom.CARD_W, cardgeom.CARD_H)
    a = np.asarray(flat.convert("L")).astype(int)
    # the dark name bar sits in the top-left, the number bar bottom-left, only when the long side is vertical
    ys, xs = np.where(a < 60)
    assert ys.size and xs.min() < 0.12 * cardgeom.CARD_W
    # 90 degrees may come out upside down: it is then the dark bar at the bottom, which the caller handles
    top = (a[: int(0.2 * cardgeom.CARD_H)] < 60).sum()
    bottom = (a[int(0.8 * cardgeom.CARD_H):] < 60).sum()
    assert top > 0 or bottom > 0


def test_flats_adds_fixed_sleeve_crops_at_card_size():
    from PIL import Image
    flat = Image.new("L", (cardgeom.CARD_W, cardgeom.CARD_H), 128)
    crops = cardgeom.sleeve_crops(flat)
    assert len(crops) == len(cardgeom.SLEEVE_SHIFTS)
    assert all(c.size == (cardgeom.CARD_W, cardgeom.CARD_H) for c in crops)
