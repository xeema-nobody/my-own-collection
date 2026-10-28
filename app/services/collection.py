from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import HTTPException

from app.db.models import CollectionIn
from app.config import settings
from app.providers.price import registry
from app.services.pricing import get_rates, latest_as_of
from app.services.valuation import grade_key, resolve_item, spread  # noqa: F401 - grade_key re-exported


PRESENT_FIELDS = ("value", "estimated", "price_kind", "source", "match", "grade_key_used", "thin",
                  "sample_size", "as_of", "observed_on", "stale", "headline_rule")
SOURCE_FIELDS = ("value", "price_kind", "match", "grade_key_used", "thin", "sample_size",
                "as_of", "observed_on", "stale")


def source_ids() -> list[str]:
    return [s.id for s in registry()]


def make_stack_key(card_id: str, variant: str | None, language: str, condition: str | None,
                   grading) -> str:
    """`grading` is a Grading model, a stored dict or None."""
    g = grading.model_dump() if hasattr(grading, "model_dump") else grading
    return "|".join(map(str, [card_id, variant or "", language, condition or "",
                              g["company"] if g else "", g["grade"] if g else "",
                              g.get("cert_number") or "" if g else ""]))


def stack_key(i: CollectionIn) -> str:
    return make_stack_key(i.card_id, i.variant, i.language, i.condition, i.grading)


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


def _comparable(best: dict, sources: dict) -> dict[str, int | None]:
    """Source values that priced the same way as the headline (same match type); a raw fallback
    next to a graded price is not a like-for-like comparison and must not trigger an outlier flag."""
    return {s: r["value"] for s, r in sources.items() if r["value"] is not None and r["match"] == best["match"]}


def _resolve_all(card, it, rates, sl, now):
    """Headline result + one result per source (own fallback chain each)."""
    best = resolve_item(card, it, rates, sl, now=now)
    return best, {s: resolve_item(card, it, rates, sl, only=s, now=now) for s in source_ids()}


async def compare_card(db, card_id: str, grading: dict | None = None, variant: str | None = None) -> dict | None:
    """Per-source comparison for one copy of a card (raw, or a given grade) whether owned or not.
    Same row shape as `present`, minus the item fields."""
    card = await db.cards.find_one({"_id": card_id})
    if not card:
        return None
    now = datetime.now(timezone.utc)
    sales = [s async for s in db.sales.find({"card_id": card_id, "sold_at": {
        "$gte": now - timedelta(days=settings.sold_window_days), "$lte": now}})]
    it = {"card_id": card_id, "quantity": 1, "variant": variant, "grading": grading}
    best, sources = _resolve_all(card, it, await get_rates(db), sales, now)
    return {**{k: best[k] for k in PRESENT_FIELDS if k in best}, "grade_key": grade_key(it),
            "sources": {s: {k: r[k] for k in SOURCE_FIELDS} for s, r in sources.items() if r["value"] is not None},
            "spread": spread(_comparable(best, sources))}


async def valuate(db, filt: dict | None = None, as_of: datetime | None = None) -> list[dict]:
    """Items joined with card + best price (see services/valuation.py). Base-currency cents for the
    whole stack; None = unpriced. `values[source]` = value when only that source is used.
    `as_of` revalues the same items at a past date from the observation log + sales (see services/movers.py)."""
    rates = await get_rates(db)
    items = await db.collection_items.find(filt or {}).to_list(None)
    ids = list({i["card_id"] for i in items})
    cards = {c["_id"]: c async for c in db.cards.find({"_id": {"$in": ids}})}
    now = as_of or datetime.now(timezone.utc)
    if as_of:
        past = await latest_as_of(db, ids, as_of.strftime("%Y-%m-%d"))
        cards = {i: {**c, "latest_price": past.get(i, {})} for i, c in cards.items()}
    since = now - timedelta(days=settings.sold_window_days)
    sales: dict[str, list[dict]] = {}
    async for s in db.sales.find({"card_id": {"$in": ids}, "sold_at": {"$gte": since, "$lte": now}}):
        sales.setdefault(s["card_id"], []).append(s)
    out = []
    for it in items:
        card = cards.get(it["card_id"])
        sl = sales.get(it["card_id"], [])
        best, sources = _resolve_all(card, it, rates, sl, now)
        cost = None
        a = it.get("acquired") or {}
        if a.get("price") is not None:
            r = rates.get(a.get("currency", "EUR"))
            cost = round(a["price"] * r * it["quantity"]) if r else None
        out.append({"item": it, "card": card, "values": {s: r["value"] for s, r in sources.items()},
                    "sources": {s: {k: r[k] for k in SOURCE_FIELDS} for s, r in sources.items() if r["value"] is not None},
                    "spread": spread(_comparable(best, sources)),
                    "cost": cost, **best, "value": best["value"]})
    return out


def present(v: dict) -> dict:
    c = v["card"] or {}
    return {**_out(v["item"]), "cost": v["cost"], "card": {k: c.get(k) for k in (
        "_id", "name", "number", "rarity", "set", "images")} if c else None,
        **{k: v[k] for k in ("value", "values", "sources", "estimated", "price_kind", "source", "match",
                             "grade_key_used", "thin", "sample_size", "as_of", "observed_on", "stale",
                             "headline_rule", "spread")}}
