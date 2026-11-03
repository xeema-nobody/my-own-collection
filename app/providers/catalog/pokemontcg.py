"""pokemontcg.io catalog adapter. API is deprecated (keys valid to 2027-03-01); swap for Scrydex later."""
import logging
from datetime import datetime, timezone
from typing import AsyncIterator

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_random_exponential

from app.config import settings
from app.providers.catalog.common import _cents, _date, _num_sort, extract_prices, norm  # noqa: F401 (re-exported)

log = logging.getLogger(__name__)
PAGE_SIZE = 100
# Upstream 500s on some page windows at pageSize=100 (flaky, data dependent). Every size divides the one
# before it, so a failed window can be re-fetched as aligned smaller pages with the same offsets.
FALLBACK_SIZES = (50, 25, 5)


class IncompletePage(Exception):
    """Some card windows could not be fetched at any page size; `missing` = [(offset, size)]."""

    def __init__(self, missing: list[tuple[int, int]]):
        self.missing = missing
        super().__init__(f"{len(missing)} card window(s) unavailable upstream: {missing}")


def _retryable(e: BaseException) -> bool:
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(e, httpx.TransportError)


def map_set(s: dict) -> dict:
    return {
        "_id": f"pokemon:{s['id']}", "tcg": "pokemon", "external_id": s["id"], "name": s["name"],
        "series": s.get("series"), "release_date": _date(s.get("releaseDate")),
        "printed_total": s.get("printedTotal"), "total": s.get("total"),
        "logo_url": (s.get("images") or {}).get("logo"),
        "symbol_url": (s.get("images") or {}).get("symbol"),
    }


def map_card(c: dict) -> dict:
    st = c.get("set") or {}
    tp = c.get("tcgplayer") or {}
    cm = c.get("cardmarket") or {}
    rules = list(c.get("rules") or [])
    for part in (c.get("abilities") or []) + (c.get("attacks") or []):
        rules.append(" ".join(filter(None, [part.get("name"), part.get("text")])))
    variants = list((tp.get("prices") or {}).keys())  # [] = card has no distinct variants
    number = c.get("number", "")
    doc = {
        "_id": f"pokemon:{c['id']}", "tcg": "pokemon", "external_id": c["id"],
        "name": c["name"], "name_norm": norm(c["name"]), "number": number,
        "number_sort": _num_sort(number), "supertype": c.get("supertype"),
        "subtypes": c.get("subtypes") or [], "types": c.get("types") or [],
        "hp": c.get("hp"), "rarity": c.get("rarity"), "artist": c.get("artist"),
        "flavor_text": c.get("flavorText"), "rules_text": rules,
        "set": {
            "id": st.get("id"), "name": st.get("name"), "series": st.get("series"),
            "release_date": _date(st.get("releaseDate")), "printed_total": st.get("printedTotal"),
            "total": st.get("total"), "logo_url": (st.get("images") or {}).get("logo"),
            "symbol_url": (st.get("images") or {}).get("symbol"),
        },
        "images": c.get("images") or {}, "variants": variants, "language": "en",
        "external_ids": {"tcgplayer_url": tp.get("url"), "cardmarket_url": cm.get("url")},
        "updated_at": datetime.now(timezone.utc),
    }
    doc["search_text"] = norm(" ".join(filter(None, [
        c["name"], st.get("name"), number, f"{number}/{st.get('printedTotal')}",
        " ".join(doc["types"]), " ".join(doc["subtypes"]), c.get("rarity"), " ".join(rules),
    ])))
    doc["_prices_raw"] = {"tcgplayer": tp, "cardmarket": cm}  # consumed by pricing, not stored on card
    return doc


class PokemonTcgCatalog:
    tcg = "pokemon"

    def __init__(self, client: httpx.AsyncClient | None = None):
        headers = {"X-Api-Key": settings.pokemontcg_api_key} if settings.pokemontcg_api_key else {}
        self._client = client or httpx.AsyncClient(
            base_url=settings.pokemontcg_base_url, headers=headers, timeout=60
        )

    async def _get(self, path: str, params: dict, attempts: int = 6) -> dict:
        async for attempt in AsyncRetrying(retry=retry_if_exception(_retryable), stop=stop_after_attempt(attempts),
                                           wait=wait_random_exponential(multiplier=1, max=30), reraise=True):
            with attempt:
                r = await self._client.get(path, params=params)
                r.raise_for_status()
                return r.json()

    async def list_sets(self) -> list[dict]:
        data = await self._get("/sets", {"orderBy": "releaseDate"})
        return [map_set(s) for s in data["data"]]

    async def _window(self, base: dict, start: int, size: int, total: int, missing: list) -> list[dict]:
        """Cards of [start, start+size) fetched as smaller aligned pages; unfetchable spans go to `missing`."""
        smaller = [s for s in FALLBACK_SIZES if s < size]
        if not smaller:
            missing.append((start, size))
            return []
        sub, out = smaller[0], []
        for off in range(start, min(start + size, total), sub):
            try:
                data = await self._get("/cards", {**base, "pageSize": sub, "page": off // sub + 1}, attempts=2)
                out += data["data"]
            except Exception as e:  # noqa: BLE001
                if not _retryable(e):
                    raise
                out += await self._window(base, off, sub, total, missing)
        return out

    async def iter_cards(self, set_id: str | None = None, only: set[str] | None = None) -> AsyncIterator[dict]:
        """Yield every card; raises IncompletePage after the last page if some windows stayed unavailable."""
        base: dict = {"orderBy": "number"}  # stable order = stable offsets across page sizes
        if set_id:
            base["q"] = f"set.id:{set_id}"
        missing: list[tuple[int, int]] = []
        start, total = 0, None
        while True:
            try:
                data = await self._get("/cards", {**base, "pageSize": PAGE_SIZE, "page": start // PAGE_SIZE + 1})
                cards, total = data["data"], data.get("totalCount", 0)
            except Exception as e:  # noqa: BLE001
                if total is None or not _retryable(e):  # first page: size unknown, nothing to salvage
                    raise
                log.warning("cards %s offset %s failed (%s); retrying with smaller pages", set_id, start, e)
                cards = await self._window(base, start, PAGE_SIZE, total, missing)
            for c in cards:
                yield map_card(c)
            start += PAGE_SIZE
            if start >= total or (not cards and not missing):
                break
        if missing:
            raise IncompletePage(missing)
