"""Artwork match: the print whose catalog art shows in the photo gets the signal (synthetic art, no network)."""
import io

import cv2
import httpx
import numpy as np
import pytest
from PIL import Image

from app.services import artmatch
from tests.test_cardgeom import H, W

ART_A = f"https://img.test/a.png"
ART_B = f"https://img.test/b.png"


def texture(seed: int, w=245, h=342) -> np.ndarray:
    """A card-sized picture full of distinct blobs (stands in for artwork)."""
    rng = np.random.default_rng(seed)
    c = np.full((h, w, 3), (200, 190, 120), np.uint8)
    for _ in range(120):
        cv2.circle(c, (int(rng.integers(0, w)), int(rng.integers(0, h))), int(rng.integers(3, 18)),
                   tuple(int(v) for v in rng.integers(0, 255, 3)), -1)
    return c


def png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    return buf.getvalue()


def photo_of(card: np.ndarray) -> bytes:
    """The card (scaled up, turned a little) on a dark table."""
    big = cv2.resize(card, (630, 880))
    bg = np.full((H, W, 3), (40, 40, 40), np.uint8)
    m = cv2.getRotationMatrix2D((315, 440), 4, 1.0)
    big = cv2.warpAffine(big, m, (630, 880), borderValue=(40, 40, 40))
    bg[300:1180, 300:930] = big
    buf = io.BytesIO()
    Image.fromarray(bg).save(buf, "JPEG", quality=92)
    return buf.getvalue()


def client(images: dict[str, bytes]) -> httpx.AsyncClient:
    def handle(req: httpx.Request) -> httpx.Response:
        b = images.get(str(req.url))
        return httpx.Response(200, content=b) if b else httpx.Response(404)
    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def card(cid: str, url: str) -> dict:
    return {"_id": cid, "images": {"small": url}}


async def test_matching_print_gets_the_signal_and_caches_art(db):
    a, b = texture(1), texture(2)
    got = await artmatch.matching(db, photo_of(a), [card("A", ART_A), card("B", ART_B)],
                                  client({ART_A: png(a), ART_B: png(b)}))
    assert got == {"A"}
    assert await db.art_cache.count_documents({}) == 2
    # second time the images come from the cache: a client with no images still works
    again = await artmatch.matching(db, photo_of(a), [card("A", ART_A), card("B", ART_B)], client({}))
    assert again == {"A"}


async def test_reprints_with_the_same_art_both_match(db):
    a = texture(3)
    got = await artmatch.matching(db, photo_of(a), [card("A", ART_A), card("B", ART_B)],
                                  client({ART_A: png(a), ART_B: png(a)}))
    assert got == {"A", "B"}


async def test_no_matching_art_gives_nothing(db):
    got = await artmatch.matching(db, photo_of(texture(4)), [card("A", ART_A), card("B", ART_B)],
                                  client({ART_A: png(texture(5)), ART_B: png(texture(6))}))
    assert got == set()


async def test_download_failures_and_missing_urls_never_raise(db):
    assert await artmatch.matching(db, photo_of(texture(1)), [card("A", ART_A), {"_id": "N"}], client({})) == set()
    assert await artmatch.matching(db, b"not an image", [card("A", ART_A)], client({})) == set()
    assert await artmatch.matching(db, photo_of(texture(1)), [], client({})) == set()
