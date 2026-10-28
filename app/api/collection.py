from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import get_db
from app.config import settings
from app.db.models import CollectionIn, CollectionPatch, RemoveIn
from app.services import collection as svc

router = APIRouter(prefix="/api/collection", tags=["collection"])


@router.post("", status_code=201)
async def add_item(body: CollectionIn):
    return await svc.add(get_db(), body)


@router.get("")
async def list_items(q: str | None = None, tcg: str | None = None, set: str | None = None,
                     graded: bool | None = None, language: str | None = None,
                     condition: str | None = None, card_id: str | None = None, sort: str = "added",
                     page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    flt: dict = {}
    if graded is not None:
        flt["grading"] = {"$ne": None} if graded else None
    if language:
        flt["language"] = language
    if condition:
        flt["condition"] = condition
    if card_id:
        flt["card_id"] = card_id
    rows = await svc.valuate(get_db(), flt)
    if tcg:
        rows = [r for r in rows if r["card"] and r["card"]["tcg"] == tcg]
    if set:
        rows = [r for r in rows if r["card"] and r["card"]["set"]["id"] == set]
    if q:
        from app.providers.catalog.pokemontcg import norm
        rows = [r for r in rows if r["card"] and norm(q) in r["card"]["search_text"]]
    keys = {"added": lambda r: r["item"]["created_at"], "value": lambda r: r["value"] or -1,
            "name": lambda r: (r["card"] or {}).get("name_norm", "")}
    rows.sort(key=keys.get(sort, keys["added"]), reverse=sort in ("added", "value"))
    total = len(rows)
    rows = rows[(page - 1) * page_size: page * page_size]
    return {"total": total, "items": [svc.present(r) for r in rows]}


@router.get("/summary")
async def summary():
    rows = await svc.valuate(get_db())
    value = {s: sum(r["values"][s] or 0 for r in rows) if any(r["values"][s] is not None for r in rows)
             else None for s in svc.source_ids()}
    cost = sum(r["cost"] or 0 for r in rows)
    best = sum(r["value"] or 0 for r in rows)
    by_source = {}
    for sid in svc.source_ids():
        have = [r for r in rows if r["values"][sid] is not None and r["value"] is not None
                and r["sources"][sid]["match"] == r["match"]]  # like-for-like only
        mine, head = sum(r["values"][sid] for r in have), sum(r["value"] for r in have)
        pct = round((mine - head) / head * 100) if head else None
        by_source[sid] = {"value": value[sid], "items": sum(1 for r in rows if r["values"][sid] is not None),
                          "vs_headline_pct": pct,  # same items only: this source vs the headline value
                          "far": pct is not None and abs(pct) > settings.outlier_pct}
    return {"by_source": by_source, "distinct": len(rows), "cards": sum(r["item"]["quantity"] for r in rows),
            "value_by_source": value, "value": best, "cost": cost,
            "pl": best - cost if cost else None,
            "value_by_kind": {k: sum(r["value"] for r in rows if r["price_kind"] == k)
                              for k in {r["price_kind"] for r in rows if r["value"] is not None}},
            "unpriced": sum(1 for r in rows if r["value"] is None),
            "estimated": sum(1 for r in rows if r["estimated"])}


@router.patch("/{item_id}")
async def patch_item(item_id: str, body: CollectionPatch):
    db = get_db()
    upd = body.model_dump(mode="json", exclude_unset=True)
    upd["updated_at"] = datetime.now(timezone.utc)
    r = await db.collection_items.update_one({"_id": svc.oid(item_id)}, {"$set": upd})
    if not r.matched_count:
        raise HTTPException(404, "item not found")
    return svc._out(await db.collection_items.find_one({"_id": svc.oid(item_id)}))


@router.post("/{item_id}/remove")
async def remove(item_id: str, body: RemoveIn):
    db = get_db()
    it = await db.collection_items.find_one({"_id": svc.oid(item_id)})
    if not it:
        raise HTTPException(404, "item not found")
    left = it["quantity"] - body.quantity
    if left <= 0:
        await db.collection_items.delete_one({"_id": it["_id"]})
        return {"deleted": True, "quantity": 0}
    await db.collection_items.update_one({"_id": it["_id"]}, {"$set": {"quantity": left}})
    return {"deleted": False, "quantity": left}


@router.delete("/{item_id}", status_code=204)
async def delete_item(item_id: str):
    r = await get_db().collection_items.delete_one({"_id": svc.oid(item_id)})
    if not r.deleted_count:
        raise HTTPException(404, "item not found")
