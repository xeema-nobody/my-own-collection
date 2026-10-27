from datetime import datetime, timedelta, timezone
from statistics import mean

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import clean, get_db
from app.db.models import SaleIn
from app.services.collection import _out
from app.services.search import SORTS, build_query

router = APIRouter(prefix="/api", tags=["cards"])


@router.get("/cards")
async def search_cards(q: str | None = None, tcg: str | None = None, set: str | None = None,
                       type: str | None = None, rarity: str | None = None,
                       supertype: str | None = None, price_min: int | None = None,
                       price_max: int | None = None, owned: bool = False, sort: str = "release",
                       page: int = Query(1, ge=1), page_size: int = Query(40, ge=1, le=100)):
    db = get_db()
    owned_ids = await db.collection_items.distinct("card_id") if owned else None
    flt = build_query(q, tcg, set, type, rarity, supertype, price_min, price_max, owned_ids)
    total = await db.cards.count_documents(flt)
    cur = (db.cards.find(flt, {"raw": 0}).sort(SORTS.get(sort, SORTS["release"]))
           .skip((page - 1) * page_size).limit(page_size))
    cards = [clean(c) async for c in cur]
    qty = {r["_id"]: r["n"] async for r in db.collection_items.aggregate([
        {"$match": {"card_id": {"$in": [c["id"] for c in cards]}}},
        {"$group": {"_id": "$card_id", "n": {"$sum": "$quantity"}}}])}
    for c in cards:
        c["owned_qty"] = qty.get(c["id"], 0)
    return {"total": total, "page": page, "page_size": page_size, "items": cards}


@router.get("/cards/{card_id}")
async def card_detail(card_id: str):
    db = get_db()
    c = await db.cards.find_one({"_id": card_id}, {"raw": 0})
    if not c:
        raise HTTPException(404, "card not found")
    stacks = [_out(i) async for i in db.collection_items.find({"card_id": card_id})]
    sales = [{**{k: v for k, v in s.items() if k != "_id"}, "id": str(s["_id"])}
             async for s in db.sales.find({"card_id": card_id}).sort("sold_at", -1).limit(50)]
    return {**clean(c), "owned": stacks, "sales": sales, "sales_stats": await _sales_stats(card_id)}


async def _sales_stats(card_id: str, last: int = 10, days: int = 90) -> list[dict]:
    db = get_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    groups: dict = {}
    async for s in db.sales.find({"card_id": card_id, "sold_at": {"$gte": since}}).sort("sold_at", -1):
        groups.setdefault((s["source"], s["grade_key"], s["currency"]), []).append(s["price"])
    return [{"source": k[0], "grade_key": k[1], "currency": k[2], "count": len(v[:last]),
             "min": min(v[:last]), "max": max(v[:last]), "avg": round(mean(v[:last]))}
            for k, v in groups.items()]


@router.get("/cards/{card_id}/prices")
async def price_history(card_id: str, source: str | None = None, grade_key: str = "raw", days: int = 365):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    flt: dict = {"card_id": card_id, "grade_key": grade_key, "as_of": {"$gte": since}}
    if source:
        flt["source"] = source
    return [{k: v for k, v in p.items() if k != "_id"}
            async for p in get_db().prices.find(flt).sort("as_of", 1)]


@router.post("/cards/{card_id}/sales", status_code=201)
async def add_sale(card_id: str, s: SaleIn):
    db = get_db()
    if not await db.cards.find_one({"_id": card_id}, {"_id": 1}):
        raise HTTPException(404, "card not found")
    doc = s.model_dump()
    doc["sold_at"] = datetime.combine(s.sold_at, datetime.min.time(), tzinfo=timezone.utc)
    await db.sales.insert_one({**doc, "card_id": card_id, "kind": "sold", "created_by": "manual"})
    return {"ok": True}


@router.get("/sets")
async def sets(tcg: str | None = None):
    flt = {"tcg": tcg} if tcg else {}
    return [clean(s) async for s in get_db().sets.find(flt).sort("release_date", -1)]


@router.get("/filters")
async def filters(tcg: str | None = None):
    db = get_db()
    f = {"tcg": tcg} if tcg else {}
    return {
        "types": sorted(await db.cards.distinct("types", f)),
        "rarities": sorted(r for r in await db.cards.distinct("rarity", f) if r),
        "supertypes": sorted(s for s in await db.cards.distinct("supertype", f) if s),
        "tcgs": sorted(await db.cards.distinct("tcg")),
    }
