"""Sale state of collection stacks (roadmap Step 6b): status + listings per platform, and the sales report.

Granularity is the stack (see decisions.md). `sale` = {status, listings[], updated_at}; absent = "none".
A sale itself is a `collection_exits` row (services/collection.remove), so sold copies leave the active
collection but stay in history. Money = integer cents; `asking_base` is the asking price per copy in the
base currency, frozen when the listing is saved (valuation never needs rates for it)."""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.db.models import BulkSaleIn, StackSaleIn
from app.services import valuation_cache
from app.services.collection import oid
from app.services.pricing import get_rates


def sale_of(item: dict) -> dict:
    return item.get("sale") or {"status": "none", "listings": []}


def status_of(item: dict) -> str:
    return sale_of(item).get("status") or "none"


def listed_base(item: dict) -> int:
    """Asking value of a listed stack in base cents: best (lowest) asking price per copy x quantity."""
    if status_of(item) != "listed":
        return 0
    asks = [l["asking_base"] for l in sale_of(item).get("listings") or [] if l.get("asking_base") is not None]
    return min(asks) * item["quantity"] if asks else 0


async def set_sale(db, item_id: str, body: StackSaleIn) -> dict:
    rates = await get_rates(db)
    listings = []
    for l in body.listings:
        d = l.model_dump(mode="json")
        rate = rates.get(l.currency)
        d["asking_base"] = round(l.asking_price * rate) if rate else None
        listings.append(d)
    doc = {"status": body.status, "listings": listings, "updated_at": datetime.now(timezone.utc)}
    try:
        r = await db.collection_items.find_one_and_update(
            {"_id": oid(item_id)},
            {"$set": {"sale": doc}} if body.status != "none" else {"$unset": {"sale": ""}},
            return_document=True)
    finally:
        valuation_cache.bump()
    if r is None:
        raise HTTPException(404, "item not found")
    return {"id": item_id, "sale": sale_of(r)}


async def bulk_set(db, body: BulkSaleIn) -> dict:
    """Set one non-listed status on many stacks. A stack that was listed loses its listings (reported)."""
    results = []
    for item_id in dict.fromkeys(body.ids):
        try:
            it = await db.collection_items.find_one({"_id": oid(item_id)}, {"sale": 1})
            if not it:
                raise HTTPException(404, "item not found")
            had = len(sale_of(it).get("listings") or [])
            await set_sale(db, item_id, StackSaleIn(status=body.status))
            results.append({"id": item_id, "ok": True, "dropped_listings": had})
        except HTTPException as e:
            results.append({"id": item_id, "ok": False, "error": e.detail})
    return {"updated": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results),
            "results": results}


async def report(db) -> dict:
    """Ready / listed (by platform) now, and sold totals from the exit history. Realised profit and
    average days listed only count sales where they are known (never counted as 0)."""
    items = [i async for i in db.collection_items.find({"sale.status": {"$in": ["ready", "listed", "reserved", "withdrawn"]}})]
    by_status: dict[str, dict] = {}
    platforms: dict[str, dict] = {}
    for it in items:
        s = status_of(it)
        e = by_status.setdefault(s, {"stacks": 0, "cards": 0})
        e["stacks"] += 1
        e["cards"] += it["quantity"]
        if s == "listed":
            for l in sale_of(it)["listings"]:
                p = platforms.setdefault(l["platform"], {"stacks": 0, "cards": 0, "value": 0})
                p["stacks"] += 1
                p["cards"] += it["quantity"]
                p["value"] += (l.get("asking_base") or 0) * it["quantity"]
    sold = [x async for x in db.collection_exits.find({"reason": "sold"})]
    rev = sum((x.get("price") or 0) * x["quantity"] for x in sold if x.get("currency", "EUR") == "EUR")
    known = [x["realised"] for x in sold if x.get("realised") is not None]
    days = [x["listed_days"] for x in sold if x.get("listed_days") is not None]
    return {
        "by_status": by_status,
        "listed_value": sum(listed_base(i) for i in items),
        "platforms": platforms,
        "sold": {"sales": len(sold), "cards": sum(x["quantity"] for x in sold), "revenue": rev,
                 "fees": sum(x.get("fees") or 0 for x in sold),
                 "shipping": sum(x.get("shipping_paid") or 0 for x in sold),
                 "realised": sum(known) if known else None, "realised_known": len(known),
                 "avg_days_to_sell": round(sum(days) / len(days), 1) if days else None},
    }
