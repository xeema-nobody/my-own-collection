"""Catalog card images (bytes). Only place that downloads them; callers cache what they keep."""
import asyncio
import logging

import httpx

log = logging.getLogger(__name__)
_SLOTS = asyncio.Semaphore(8)  # polite: a handful of image downloads at a time
MAX_BYTES = 2_000_000


async def fetch_image(url: str, client: httpx.AsyncClient) -> bytes | None:
    """The image at `url`, or None on any failure (an unreachable image only means one less comparison)."""
    async with _SLOTS:
        try:
            r = await client.get(url)
            if r.status_code == 200 and len(r.content) <= MAX_BYTES:
                return r.content
        except httpx.HTTPError as e:
            log.info("card image %s failed: %s", url, e)
    return None


def new_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=15, follow_redirects=True, transport=transport)
