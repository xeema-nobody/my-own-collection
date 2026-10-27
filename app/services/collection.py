from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException

from app.db.models import CollectionIn
from app.services.pricing import get_rates, price_for

SOURCES = ("tcgplayer", "cardmarket")


def stack_key(i: CollectionIn) -> str:
    g = i.grading
    return "|".join(map(str, [i.card_id, i.variant, i.language, i.condition or "",
                              g.company if g else "", g.grade if g else "",
                              g.cert_number if g and g.cert_number else ""]))


def grade_key(item: dict) -> str:
    g = item.get("grading")
    return "raw" if not g else f"{g['company']}{g['grade']:g}"


async def add(db, i: CollectionIn) -> dict:
    if not await db.cards.find_one({"_id": i.card_id}, {"_id": 1}):
        raise HTTPException(404, "card not found")
    now = datetime.now(timezone.utc)
    key = stack_key(i)
    doc = i.model_dump(mode="json", exclude={"quantity"})
    await db.collection_items.update_one(
        {"stack_key": key},
        {"$inc": {"quantity": i.quantity},
         "$setOnInsert": {**doc, "stack_key": key, "created_at": now}, "$set": {"updated_at": now}},
        upsert=True)
    return _out(await db.collection_items.find_one({"stack_key": key}))


def _out(d: dict) -> dict:
    d = dict(d)
    d["id"] = str(d.pop("_id"))
    d.pop("stack_key", None)
    return d


def oid(id_: str) -> ObjectId:
    try:
        return ObjectId(id_)
    except Exception:
        raise HTTPException(404, "item not found")


async def valuate(db, filt: dict | None = None) -> list[dict]:
    """Items joined with card + per-source value (base-currency cents; None = unpriced)."""
    rates = await get_rates(db)
    items = await db.collection_items.find(filt or {}).to_list(None)
    cards = {c["_id"]: c async for c in db.cards.find({"_id": {"$in": list({i["card_id"] for i in items})}})}
    out = []
    for it in items:
        card = cards.get(it["card_id"])
        values, estimated = {}, False
        for s in SOURCES:
            v, est = price_for(card, s, it["variant"], rates) if card else (None, False)
            values[s] = None if v is None else v * it["quantity"]
            estimated = estimated or est or (it.get("grading") is not None and v is not None)
        best = values["cardmarket"] if values["cardmarket"] is not None else values["tcgplayer"]
        cost = None
        a = it.get("acquired") or {}
        if a.get("price") is not None:
            r = rates.get(a.get("currency", "EUR"))
            cost = round(a["price"] * r * it["quantity"]) if r else None
        out.append({"item": it, "card": card, "values": values, "value": best,
                    "estimated": estimated, "cost": cost})
    return out


def present(v: dict) -> dict:
    c = v["card"] or {}
    return {**_out(v["item"]), "value": v["value"], "values": v["values"], "cost": v["cost"],
            "estimated": v["estimated"],
            "card": {k: c.get(k) for k in ("_id", "name", "number", "rarity", "set", "images")}
                    if c else None}
