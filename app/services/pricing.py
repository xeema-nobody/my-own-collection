"""Price storage + valuation. Money = integer cents + currency. Missing price = None, never 0."""
from pymongo import UpdateOne

from app.providers.catalog.pokemontcg import extract_prices
from app.services.fx import convert, rates_to_base


async def store_card_prices(db, card_doc: dict, rates: dict) -> int:
    """Upsert price points for one catalog card doc and denormalise latest_price onto the card."""
    points = extract_prices(card_doc)
    ops, latest = [], {}
    for p in points:
        key = {"card_id": card_doc["_id"], "variant": p["variant"], "source": p["source"],
               "kind": "market", "grade_key": "raw", "as_of": p["as_of"]}
        body = {k: v for k, v in p.items() if k not in ("source", "variant", "as_of")}
        ops.append(UpdateOne(key, {"$set": body, "$currentDate": {"fetched_at": True}}, upsert=True))
        latest.setdefault(p["source"], {})[p["variant"]] = {
            "market": p.get("market"), "low": p.get("low"), "avg": p.get("avg"),
            "high": p.get("high"), "currency": p["currency"], "as_of": p["as_of"]}
    if ops:
        await db.prices.bulk_write(ops, ordered=False)
    best = None
    for src in ("cardmarket", "tcgplayer"):
        for v in (latest.get(src) or {}).values():
            best = convert(v["market"], v["currency"], rates)
            if best is not None:
                break
        if best is not None:
            break
    await db.cards.update_one({"_id": card_doc["_id"]},
                              {"$set": {"latest_price": latest, "price_base": best}})
    return len(points)


def price_for(card: dict, source: str, variant: str, rates: dict) -> tuple[int | None, bool]:
    """Value (base-currency cents) of one copy via a source; bool = estimated (variant fallback)."""
    variants = (card.get("latest_price") or {}).get(source) or {}
    if not variants:
        return None, False
    if source == "cardmarket":
        v, est = variants.get("default"), False
    else:
        v = variants.get(variant)
        est = v is None
        if v is None:
            v = next(iter(variants.values()))
    return convert(v["market"], v["currency"], rates), est


async def get_rates(db) -> dict:
    return await rates_to_base(db, {"USD", "EUR"})
