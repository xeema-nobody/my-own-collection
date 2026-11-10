"""Artwork match of a scan photo against the prints of the name read (fallback when the number line is unread).

Catalog art crops are cached in `art_cache` (_id = image url), so every image is downloaded once."""
import asyncio
import logging

from app.providers.catalog.images import fetch_image, new_client
from app.providers.ocr import imagematch

log = logging.getLogger(__name__)
MIN_INLIERS = 12   # below this the best art is no evidence (a card not in the catalog scores ~5)
KEEP_SHARE = 0.2   # prints within this share of the best score get the signal (reprints share their art)
LIMIT = 80


def url_of(c: dict) -> str | None:
    return (c.get("images") or {}).get("small")


async def _art(db, client, url: str) -> bytes | None:
    hit = await db.art_cache.find_one({"_id": url})
    if hit:
        return hit["png"]
    data = await fetch_image(url, client)
    png = await asyncio.to_thread(imagematch.art_png, data) if data else None
    if png:
        await db.art_cache.update_one({"_id": url}, {"$set": {"png": png}}, upsert=True)
    return png


async def matching(db, image: bytes, cards: list[dict], client=None) -> set[str]:
    """Ids of the cards whose artwork clearly matches the photo (empty when nothing does or anything fails)."""
    cards = [c for c in cards[:LIMIT] if url_of(c)]
    if not cards:
        return set()
    try:
        photo = await asyncio.to_thread(imagematch.photo_arts, image)
        if not photo:
            return set()
        own = client is None
        client = client or new_client()
        try:
            arts = await asyncio.gather(*[_art(db, client, url_of(c)) for c in cards])
        finally:
            if own:
                await client.aclose()
        scores = await asyncio.gather(*[asyncio.to_thread(imagematch.score, photo, a) if a else _zero() for a in arts])
    except Exception:  # noqa: BLE001 - the art match is a bonus, scanning must never fail on it
        log.warning("art match failed", exc_info=True)
        return set()
    best = max(scores, default=0)
    if best < MIN_INLIERS:
        return set()
    return {c["_id"] for c, s in zip(cards, scores) if s >= max(MIN_INLIERS, KEEP_SHARE * best)}


async def _zero() -> int:
    return 0
