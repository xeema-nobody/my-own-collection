from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import HTTPException

from app.db.models import CollectionIn
from app.services import acquisition
from app.services import slab
from app.config import settings
from app.providers.price import registry
from app.services import valuation_cache
from app.services.pricing import get_rates, latest_as_of
from app.services.valuation import grade_key, resolve_item, spread  # noqa: F401 - grade_key re-exported


PRESENT_FIELDS = ("value", "estimated", "price_kind", "source", "match", "grade_key_used", "thin",
                  "sample_size", "as_of", "observed_on", "stale", "headline_rule", "needs_price", "ref_raw_value",
                  "ref_raw_source")
SOURCE_FIELDS = ("value", "price_kind", "match", "grade_key_used", "thin", "sample_size",
                "as_of", "observed_on", "stale")


def source_ids() -> list[str]:
    return [s.id for s in registry()]


def _company(g: dict | None) -> str:
    """Two different graders filed under OTHER must not merge into one stack."""
    if not g:
        return ""
    name = (g.get("grader_name") or "").strip().lower() if g["company"] == "OTHER" else ""
    return f"OTHER:{name}" if name else g["company"]


def make_stack_key(card_id: str, variant: str | None, language: str, condition: str | None,
                   grading) -> str:
    """`grading` is a Grading model, a stored dict or None."""
    g = grading.model_dump() if hasattr(grading, "model_dump") else grading
    return "|".join(map(str, [card_id, variant or "", language, condition or "",
                              _company(g), g["grade"] if g else "",
                              g.get("cert_number") or "" if g else ""]))


def stack_key(i: CollectionIn) -> str:
    return make_stack_key(i.card_id, i.variant, i.language, i.condition, i.grading)


async def add(db, i: CollectionIn) -> dict:
    try:
        return await _add(db, i)
    finally:
        valuation_cache.bump()


async def _add(db, i: CollectionIn) -> dict:
    if not await db.cards.find_one({"_id": i.card_id}, {"_id": 1}):
        raise HTTPException(404, "card not found")
    now = datetime.now(timezone.utc)
    key = stack_key(i)
    existing = await db.collection_items.find_one({"stack_key": key})
    if existing is not None and i.grading and i.grading.cert_number:
        # one physical slab: scanning it again changes nothing (idempotent), the caller is told
        return _out(existing) | {"type_conflict": False, "duplicate": True}
    doc = i.model_dump(mode="json", exclude={"quantity"})
    if doc.get("grading"):
        doc["grading"] = await slab.enrich_grading(db, doc["grading"])
    if existing is None:
        await db.collection_items.update_one(
            {"stack_key": key},
            {"$inc": {"quantity": i.quantity},
             "$setOnInsert": {**doc, "stack_key": key, "created_at": now}, "$set": {"updated_at": now}},
            upsert=True)
        return _out(await db.collection_items.find_one({"stack_key": key})) | {"type_conflict": False}
    # more copies join an existing stack: cost = weighted average, mismatches are reported not guessed
    merged, conflict = acquisition.weighted_merge(
        existing.get("acquired"), doc.get("acquired"), existing["quantity"], i.quantity)
    await db.collection_items.update_one(
        {"_id": existing["_id"]}, {"$inc": {"quantity": i.quantity}, "$set": {"acquired": merged, "updated_at": now}})
    before = acquisition.norm(existing.get("acquired"))
    if merged != before:
        await acquisition.log_edit(db, existing, "merge", before, merged)
    return _out(await db.collection_items.find_one({"_id": existing["_id"]})) | {"type_conflict": conflict}


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


def is_sealed(row: dict) -> bool:
    return (row.get("card") or {}).get("kind") == "sealed"


def by_kind(rows: list[dict], kind: str) -> list[dict]:
    """`cards` (default everywhere: Value, P/L, snapshots, movers), `sealed` (sealed products) or `all`."""
    if kind == "all":
        return rows
    out = [r for r in rows if is_sealed(r) == (kind == "sealed")]
    return rows if len(out) == len(rows) else out   # same list when nothing is dropped (cache identity)


async def valuate(db, filt: dict | None = None, as_of: datetime | None = None, kind: str = "cards") -> list[dict]:
    """Items joined with card + best price (see services/valuation.py). Base-currency cents for the
    whole stack; None = unpriced. `values[source]` = value when only that source is used.
    `as_of` revalues the same items at a past date from the observation log + sales (see services/movers.py).
    `kind` keeps sealed products out of every card total unless asked (`sealed` / `all`).
    The unfiltered, current valuation is cached (services/valuation_cache.py): treat its rows as read-only."""
    if not filt and as_of is None:
        return by_kind(await valuation_cache.get_rows(db, _valuate_all), kind)
    return by_kind(await valuate_items(db, await db.collection_items.find(filt or {}).to_list(None), as_of), kind)


async def _valuate_all(db) -> list[dict]:
    return await valuate_items(db, await db.collection_items.find({}).to_list(None))


async def valuate_items(db, items: list[dict], as_of: datetime | None = None) -> list[dict]:
    """`valuate` over any list of item-shaped dicts (collection stacks, or virtual wishlist items)."""
    rates = await get_rates(db)
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
        if (a.get("price") or 0) > 0:  # blank or 0 = "no cost" (a gift / pulled card), never a real 0 cost for P/L
            r = rates.get(a.get("currency", "EUR"))
            cost = round(a["price"] * r * it["quantity"]) if r else None
        out.append({"item": it, "card": card, "values": {s: r["value"] for s, r in sources.items()},
                    "sources": {s: {k: r[k] for k in SOURCE_FIELDS} for s, r in sources.items() if r["value"] is not None},
                    "spread": spread(_comparable(best, sources)),
                    "cost": cost, **best, "value": best["value"]})
    return out


async def valuate_wishlist(db, as_of: datetime | None = None) -> list[dict]:
    """Wishlist entries valued like one owned copy (virtual item, `_id` = the wish id)."""
    items = [{"_id": w["_id"], "card_id": w["card_id"], "variant": w.get("variant"), "grading": w.get("grading"),
              "language": "en", "condition": None, "quantity": 1} async for w in db.wishlist.find()]
    return await valuate_items(db, items, as_of)


def present(v: dict) -> dict:
    c = v["card"] or {}
    pl = None if v["value"] is None or v["cost"] is None else v["value"] - v["cost"]
    return {**_out(v["item"]), "cost": v["cost"], "pl": pl, "card": {k: c.get(k) for k in (
        "_id", "name", "number", "rarity", "set", "images", "kind", "sealed_type", "edition")} if c else None,
        **{k: v[k] for k in ("value", "values", "sources", "estimated", "price_kind", "source", "match",
                             "grade_key_used", "thin", "sample_size", "as_of", "observed_on", "stale",
                             "headline_rule", "spread", "needs_price", "ref_raw_value", "ref_raw_source")}}


async def needs_price_card_ids(db) -> list[str]:
    """Owned cards with a graded stack that has no graded price (what "Fetch missing prices" targets)."""
    return sorted({v["item"]["card_id"] for v in await valuate(db) if v["needs_price"]})


def realised(acquired: dict | None, qty: int, price: int | None, currency: str,
             fees: int | None, shipping: int | None) -> int | None:
    """Profit of a sale in cents: price x qty - fees - shipping - cost. None (never 0) when the sale price or the
    cost is unknown, or the cost is in another currency than the sale (no rate applied here)."""
    a = acquired or {}
    if price is None or (a.get("price") or 0) <= 0 or a.get("currency", "EUR") != currency:
        return None
    return price * qty - (fees or 0) - (shipping or 0) - a["price"] * qty


async def remove(db, item_id: str, quantity: int = 1, reason: str = "removed", price: int | None = None,
                  currency: str = "EUR", date=None, note: str | None = None, platform: str | None = None,
                  fees: int | None = None, shipping_paid: int | None = None, opening_id: str | None = None) -> dict:
    """Take copies out of a stack (sold / gifted / removed). Always logs a `collection_exits` row with the
    stack snapshot (cost basis included) so nothing leaves silently; asking for more than owned removes all."""
    it = await db.collection_items.find_one({"_id": oid(item_id)})
    if not it:
        raise HTTPException(404, "item not found")
    qty = min(quantity, it["quantity"])
    now = datetime.now(timezone.utc)
    sold = reason == "sold"
    day = date.isoformat() if date else now.date().isoformat()
    listings = (it.get("sale") or {}).get("listings") or []
    left = it["quantity"] - qty
    listed_days = None
    if sold:
        starts = [l["listed_at"] for l in listings if l.get("listed_at") and (not platform or l["platform"] == platform)]
        if starts:
            listed_days = max((datetime.fromisoformat(day) - datetime.fromisoformat(min(starts))).days, 0)
    await db.collection_exits.insert_one({
        "card_id": it["card_id"], "stack_key": it.get("stack_key"), "variant": it.get("variant"),
        "language": it.get("language"), "condition": it.get("condition"), "grading": it.get("grading"),
        "acquired": it.get("acquired"), "quantity": qty, "reason": reason,
        "price": price if sold else None, "currency": currency,
        "date": day, "note": note, "created_at": now,
        "platform": platform if sold else None, "fees": fees if sold else None,
        "shipping_paid": shipping_paid if sold else None,
        "realised": realised(it.get("acquired"), qty, price, currency, fees, shipping_paid) if sold else None,
        "listed_days": listed_days, "opening_id": opening_id,
        # other platforms still listing a stack that is now gone: the user must delist there
        "delist": sorted({l["platform"] for l in listings if l["platform"] != platform}) if sold and left <= 0 else []})
    try:
        if left <= 0:
            await db.collection_items.delete_one({"_id": it["_id"]})
            await db.photos.delete_many({"stack_id": str(it["_id"])})  # photos go with the stack
        else:
            await db.collection_items.update_one({"_id": it["_id"]}, {"$set": {"quantity": left, "updated_at": now}})
    finally:
        valuation_cache.bump()
    return {"deleted": left <= 0, "quantity": max(left, 0), "removed": qty,
            "realised": realised(it.get("acquired"), qty, price, currency, fees, shipping_paid) if sold else None,
            "delist": sorted({l["platform"] for l in listings if l["platform"] != platform}) if sold and left <= 0 else []}


async def remove_many(db, ids: list[str], reason: str = "removed", note: str | None = None) -> dict:
    """Remove whole stacks, one exit row each. A bad or missing id is reported, the rest still go through."""
    results, copies = [], 0
    for item_id in dict.fromkeys(ids):
        try:
            it = await db.collection_items.find_one({"_id": oid(item_id)}, {"quantity": 1})
            if not it:
                raise HTTPException(404, "item not found")
            r = await remove(db, item_id, quantity=it["quantity"], reason=reason, note=note)
            copies += r["removed"]
            results.append({"id": item_id, "ok": True, "removed": r["removed"]})
        except HTTPException as e:
            results.append({"id": item_id, "ok": False, "error": e.detail})
    return {"removed": sum(r["ok"] for r in results), "copies": copies,
            "failed": sum(not r["ok"] for r in results), "results": results}


async def exits(db, limit: int = 100) -> list[dict]:
    """Recent exits with a card label, newest first."""
    rows = [r async for r in db.collection_exits.find().sort("created_at", -1).limit(limit)]
    cards = {c["_id"]: c async for c in db.cards.find({"_id": {"$in": list({r["card_id"] for r in rows})}},
                                                       {"name": 1, "number": 1, "set.name": 1, "images": 1})}
    out = []
    for r in rows:
        c = cards.get(r["card_id"]) or {}
        out.append({"id": str(r.pop("_id")), **{k: r.get(k) for k in (
            "card_id", "quantity", "reason", "price", "currency", "date", "note", "condition", "grading", "acquired",
            "platform", "fees", "shipping_paid", "realised", "listed_days", "delist", "opening_id")},
            "created_at": r["created_at"].isoformat(),
            "card": {"name": c.get("name"), "number": c.get("number"), "set": (c.get("set") or {}).get("name"),
                     "image": (c.get("images") or {}).get("small")} if c else None})
    return out
