"""Price storage + valuation. Money = integer cents + currency. Missing price = None, never 0.

`prices` is an observation log keyed (card_id, variant, source, kind, grade_key, observed_on):
re-storing on the same UTC day overwrites, a new day adds a point.
`cards.latest_price[source][kind][grade_slot][variant_slot]` denormalises the newest value.
"""
from datetime import datetime, timezone

from pymongo import UpdateOne

from app.providers.catalog.pokemontcg import extract_prices
from app.services.fx import convert, rates_to_base

NO_VARIANT = "_"  # latest_price slot for variant=None
BEST_SOURCES = ("cardmarket", "tcgplayer")  # headline price preference
PRICE_SCHEMA = 2


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def grade_slot(grade_key: str) -> str:
    """Field-name safe grade key ('PSA9.5' -> 'PSA9_5'); dots are path separators in Mongo."""
    return grade_key.replace(".", "_")


def variant_slot(variant: str | None) -> str:
    return variant or NO_VARIANT


def point_key(card_id: str, p: dict, observed_on: str) -> dict:
    return {"card_id": card_id, "variant": p.get("variant"), "source": p["source"],
            "kind": p.get("kind", "market"), "grade_key": p.get("grade_key", "raw"),
            "observed_on": observed_on}


def build_latest(points: list[dict]) -> dict:
    latest: dict = {}
    for p in points:
        slot = (latest.setdefault(p["source"], {}).setdefault(p.get("kind", "market"), {})
                .setdefault(grade_slot(p.get("grade_key", "raw")), {}))
        slot[variant_slot(p.get("variant"))] = {
            "market": p.get("market"), "low": p.get("low"), "avg": p.get("avg"),
            "high": p.get("high"), "currency": p["currency"], "as_of": p.get("as_of")}
    return latest


def best_base(latest: dict, rates: dict) -> int | None:
    """Headline raw market price in base-currency cents: cardmarket, else tcgplayer."""
    for src in BEST_SOURCES:
        for v in (((latest.get(src) or {}).get("market") or {}).get("raw") or {}).values():
            best = convert(v.get("market"), v["currency"], rates)
            if best is not None:
                return best
    return None


async def store_card_prices(db, card_doc: dict, rates: dict, observed_on: str | None = None) -> int:
    """Upsert today's price points for one catalog card doc and denormalise latest_price onto the card."""
    observed_on = observed_on or today()
    points = extract_prices(card_doc)
    ops = []
    for p in points:
        body = {k: v for k, v in p.items() if k not in ("source", "variant", "kind", "grade_key")}
        ops.append(UpdateOne(point_key(card_doc["_id"], p, observed_on),
                             {"$set": body, "$currentDate": {"fetched_at": True}}, upsert=True))
    if ops:
        await db.prices.bulk_write(ops, ordered=False)
    latest = build_latest(points)
    await db.cards.update_one({"_id": card_doc["_id"]},
                              {"$set": {"latest_price": latest, "price_base": best_base(latest, rates),
                                        "price_schema": PRICE_SCHEMA}})
    return len(points)


def price_for(card: dict, source: str, variant: str | None, rates: dict, grade_key: str = "raw",
              kind: str = "market") -> tuple[int | None, bool]:
    """Value (base-currency cents) of one copy via a source; bool = estimated (variant fallback)."""
    variants = ((((card.get("latest_price") or {}).get(source) or {}).get(kind) or {})
                .get(grade_slot(grade_key)) or {})
    if not variants:
        return None, False
    v = variants.get(variant_slot(variant))
    est = False
    if v is None:
        if NO_VARIANT in variants:  # source has one price for every variant
            v = variants[NO_VARIANT]
        else:
            v, est = next(iter(variants.values())), True
    return convert(v.get("market"), v["currency"], rates), est


async def get_rates(db) -> dict:
    return await rates_to_base(db, {"USD", "EUR"})
