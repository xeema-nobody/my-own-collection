"""Persisted card -> product-page matches for scraped sources (collection `product_matches`).

A `user` match always wins; `auto` matches (adapter resolved unambiguously) just save the next search.
Pending candidates (needs_match) are kept alongside so the UI can offer a picker."""
from dataclasses import asdict
from datetime import datetime, timezone
from urllib.parse import urlparse

from pymongo.errors import DuplicateKeyError

from app.providers.price.base import AdapterResult

# source -> (hosts, product path marker). Same hosts as the fetcher whitelist (fetcher/sites.py).
MATCHABLE: dict[str, tuple[tuple[str, ...], str]] = {
    "pricecharting": (("pricecharting.com",), "/game/"),
    "cardmarket_web": (("cardmarket.com",), "/Products/Singles/"),
}


class InvalidMatch(ValueError):
    """Source not matchable or url not a product page of that source."""


def validate_url(source: str, url: str) -> str:
    if source not in MATCHABLE:
        raise InvalidMatch(f"{source} has no product matching")
    hosts, marker = MATCHABLE[source]
    u = urlparse(url.strip())
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not any(host == h or host.endswith("." + h) for h in hosts):
        raise InvalidMatch(f"url must be https on {hosts[0]}")
    if marker not in u.path:
        raise InvalidMatch(f"not a {source} product url (expected '{marker}' in path)")
    return url.strip()


def _key(card_id: str, source: str) -> str:
    return f"{card_id}|{source}"


def _out(d: dict | None) -> dict:
    if not d:
        return {"url": None, "confirmed_by": None, "candidates": [], "updated_at": None}
    return {"url": d.get("url"), "confirmed_by": d.get("confirmed_by"),
            "candidates": d.get("candidates", []), "updated_at": d.get("updated_at")}


async def get_matches(db, card_id: str) -> dict[str, dict]:
    """One entry per matchable source (empty entry when nothing stored)."""
    rows = {r["source"]: r async for r in db.product_matches.find({"card_id": card_id})}
    return {s: _out(rows.get(s)) for s in MATCHABLE}


async def known_url(db, card_id: str, source: str) -> str | None:
    d = await db.product_matches.find_one({"_id": _key(card_id, source)}, {"url": 1})
    return d.get("url") if d else None


async def confirm(db, card_id: str, source: str, url: str) -> dict:
    url = validate_url(source, url)
    await db.product_matches.update_one(
        {"_id": _key(card_id, source)},
        {"$set": {"card_id": card_id, "source": source, "url": url, "confirmed_by": "user",
                  "candidates": [], "updated_at": datetime.now(timezone.utc)}}, upsert=True)
    return _out(await db.product_matches.find_one({"_id": _key(card_id, source)}))


async def clear(db, card_id: str, source: str) -> None:
    if source not in MATCHABLE:
        raise InvalidMatch(f"{source} has no product matching")
    await db.product_matches.delete_one({"_id": _key(card_id, source)})


async def record_result(db, card_id: str, source: str, result: AdapterResult) -> None:
    """Persist what an adapter run learned. Only `ok` (auto url) and `needs_match` (candidates)
    matter; a user-confirmed url is never replaced."""
    if source not in MATCHABLE or result.status not in ("ok", "needs_match"):
        return
    now = datetime.now(timezone.utc)
    if result.status == "needs_match":
        await db.product_matches.update_one(
            {"_id": _key(card_id, source)},
            {"$set": {"card_id": card_id, "source": source, "updated_at": now,
                      "candidates": [asdict(c) for c in result.candidates]},
             "$setOnInsert": {"url": None, "confirmed_by": None}}, upsert=True)
        return
    if not result.url:
        return
    try:
        await db.product_matches.update_one(
            {"_id": _key(card_id, source), "confirmed_by": {"$ne": "user"}},
            {"$set": {"card_id": card_id, "source": source, "url": result.url, "confirmed_by": "auto",
                      "candidates": [], "updated_at": now}}, upsert=True)
    except DuplicateKeyError:
        pass   # a user-confirmed match exists: keep it
