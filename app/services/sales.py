"""Scraped sold listings + chart history seed.

`sales` rows are individual completed sales, deduped on (card_id, source, listing_id); manual
sales have no listing_id and are exempt from the unique index (partial). Chart seed rows are
`prices` observations flagged `seed: True` so they never shadow or overwrite a real observation.
"""
from datetime import date, datetime, timezone

from pymongo import UpdateOne

from app.providers.price.base import Sale


def _utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


async def store_sales(db, card_id: str, sales: list[Sale]) -> int:
    """Upsert scraped sales; returns the number of new rows."""
    if not sales:
        return 0
    now = datetime.now(timezone.utc)
    ops = [UpdateOne(
        {"card_id": card_id, "source": s.source, "listing_id": s.listing_id},
        {"$set": {"variant": None, "grade_key": s.grade_key, "price": s.price, "currency": s.currency,
                  "title": s.title, "sold_at": _utc(s.sold_on), "kind": "sold", "created_by": "scraper",
                  "fetched_at": now},
         "$setOnInsert": {"first_seen": now}}, upsert=True) for s in sales]
    res = await db.sales.bulk_write(ops, ordered=False)
    return res.upserted_count


async def store_chart_seed(db, card_id: str, source: str, chart: list[tuple[date, int]],
                           currency: str = "USD") -> int:
    """Seed raw market history from a site chart; returns the number of new observations.

    `$setOnInsert` only: a day that already has an observation (real or seed) is left alone.
    Does not touch `latest_price` / `price_base`."""
    if not chart:
        return 0
    now = datetime.now(timezone.utc)
    ops = [UpdateOne(
        {"card_id": card_id, "variant": None, "source": source, "kind": "market", "grade_key": "raw",
         "observed_on": d.isoformat()},
        {"$setOnInsert": {"market": cents, "currency": currency, "as_of": _utc(d), "seed": True,
                          "fetched_at": now}}, upsert=True) for d, cents in chart]
    res = await db.prices.bulk_write(ops, ordered=False)
    return res.upserted_count
