"""pokemontcg.io catalog adapter. API is deprecated (keys valid to 2027-03-01); swap for Scrydex later."""
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import AsyncIterator

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential

from app.config import settings

log = logging.getLogger(__name__)
PAGE_SIZE = 100


def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _retryable(e: BaseException) -> bool:
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(e, httpx.TransportError)


def _cents(v) -> int | None:
    # Upstream sends 0 for "no data"; a price of 0 is never real, so it is missing (None).
    return None if not v else round(float(v) * 100)


def _date(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.strptime(s[:10].replace("/", "-"), "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _num_sort(number: str) -> int:
    m = re.search(r"\d+", number or "")
    return int(m.group()) if m else 0


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


def extract_prices(doc: dict) -> list[dict]:
    """Aggregate price points (kind=market, raw) from the embedded tcgplayer/cardmarket blocks."""
    out: list[dict] = []
    raw = doc["_prices_raw"]
    tp, cm = raw["tcgplayer"], raw["cardmarket"]
    base = {"kind": "market", "grade_key": "raw"}
    as_of = _date(tp.get("updatedAt"))
    for variant, p in (tp.get("prices") or {}).items():
        out.append({**base, "source": "tcgplayer", "variant": variant, "currency": "USD", "as_of": as_of,
                    "url": tp.get("url"), "low": _cents(p.get("low")), "avg": _cents(p.get("mid")),
                    "high": _cents(p.get("high")), "market": _cents(p.get("market"))})
    cp = cm.get("prices") or {}
    if cp:  # one price per card, no per-variant split
        out.append({**base, "source": "cardmarket", "variant": None, "currency": "EUR",
                    "as_of": _date(cm.get("updatedAt")), "url": cm.get("url"),
                    "low": _cents(cp.get("lowPrice")), "avg": _cents(cp.get("averageSellPrice")),
                    "trend": _cents(cp.get("trendPrice")), "market": _cents(cp.get("trendPrice")),
                    "avg7": _cents(cp.get("avg7")), "avg30": _cents(cp.get("avg30"))})
    return out


class PokemonTcgCatalog:
    tcg = "pokemon"

    def __init__(self, client: httpx.AsyncClient | None = None):
        headers = {"X-Api-Key": settings.pokemontcg_api_key} if settings.pokemontcg_api_key else {}
        self._client = client or httpx.AsyncClient(
            base_url=settings.pokemontcg_base_url, headers=headers, timeout=60
        )

    @retry(retry=retry_if_exception(_retryable), stop=stop_after_attempt(6),
           wait=wait_random_exponential(multiplier=1, max=30), reraise=True)
    async def _get(self, path: str, params: dict) -> dict:
        r = await self._client.get(path, params=params)
        r.raise_for_status()
        return r.json()

    async def list_sets(self) -> list[dict]:
        data = await self._get("/sets", {"orderBy": "releaseDate"})
        return [map_set(s) for s in data["data"]]

    async def iter_cards(self, set_id: str | None = None) -> AsyncIterator[dict]:
        page = 1
        params: dict = {"pageSize": PAGE_SIZE}
        if set_id:
            params["q"] = f"set.id:{set_id}"
        while True:
            data = await self._get("/cards", {**params, "page": page})
            for c in data["data"]:
                yield map_card(c)
            if page * PAGE_SIZE >= data.get("totalCount", 0) or not data["data"]:
                return
            page += 1
