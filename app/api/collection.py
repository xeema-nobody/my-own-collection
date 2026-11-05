from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from app.services import valuation_cache
from app.api.deps import get_db
from app.config import settings
from app.db.models import BulkAcquiredIn, CollectionIn, CollectionPatch, PresetIn, RemoveIn
from app.services import acquisition
from app.services import collection_query as cq
from app.services import presets
from app.services import collection as svc
from app.services import portability
from app.services.price_fetch import price_freshness

router = APIRouter(prefix="/api/collection", tags=["collection"])


@router.post("", status_code=201)
async def add_item(body: CollectionIn):
    return await svc.add(get_db(), body)


MAX_UPLOAD = 5_000_000


@router.get("/export")
async def export(format: str = Query("json", pattern="^(json|csv)$")):
    db = get_db()
    items = await portability.export_items(db)
    body = await portability.to_csv(db, items) if format == "csv" else portability.to_json(items)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Response(body, media_type="text/csv" if format == "csv" else "application/json",
                    headers={"Content-Disposition": f'attachment; filename="collection-{day}.{format}"'})


@router.post("/import")
async def import_(request: Request, format: str = Query("json", pattern="^(json|csv)$"),
                  mode: str = Query("set", pattern="^(set|add)$")):
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD:
        raise HTTPException(413, "file too large")
    raw = bytearray()  # raw file body (no multipart dependency); capped while streaming
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(413, "file too large")
    raw = bytes(raw)
    try:
        rows = portability.parse(raw, format)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return await portability.import_items(get_db(), rows, mode)


@router.get("")
async def list_items(q: str | None = None, tcg: str | None = None, set: str | None = None,
                     rarity: str | None = None, type: str | None = None,
                     graded: bool | None = None, grader: str | None = None, grade: str | None = None,
                     language: str | None = None, condition: str | None = None, card_id: str | None = None,
                     needs_price: bool | None = None, stale: bool | None = None, cost_missing: bool | None = None,
                     acquisition_type: str | None = Query(None, alias="acquisition", pattern="^(purchased|pulled|traded|gift|other|unset)$"),
                     price_min: int | None = Query(None, ge=0), price_max: int | None = Query(None, ge=0),
                     pl: str | None = Query(None, pattern="^(positive|negative)$"),
                     sort: str = Query("added", pattern=f"^({'|'.join(cq.SORTS)})$"),
                     order: str | None = Query(None, pattern="^(asc|desc)$"),
                     page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    """Filtered, sorted page of valuated stacks + `totals` for the whole filtered set."""
    query = cq.Query(q=q, tcg=tcg, set=set, rarity=rarity, type=type, graded=graded, grader=grader, grade=grade,
                     language=language, condition=condition, card_id=card_id, needs_price=needs_price, stale=stale,
                     cost_missing=cost_missing, acquisition=acquisition_type, price_min=price_min,
                     price_max=price_max, pl=pl, sort=sort, order=order, page=page, page_size=page_size)
    return cq.query(await svc.valuate(get_db()), query)


@router.get("/facets")
async def facets():
    """Distinct sets / rarities / types / languages / conditions / graders / grades with stack counts."""
    return cq.facets(await svc.valuate(get_db()))


@router.get("/presets")
async def list_presets(scope: str = Query("collection", pattern="^(collection|wishlist)$")):
    return await presets.list_(get_db(), scope)


@router.post("/presets", status_code=201)
async def save_preset(body: PresetIn):
    return await presets.create(get_db(), body)


@router.delete("/presets/{preset_id}", status_code=204)
async def delete_preset(preset_id: str):
    await presets.remove(get_db(), preset_id)


@router.get("/summary")
async def summary():
    rows = await svc.valuate(get_db())
    value = {s: sum(r["values"][s] or 0 for r in rows) if any(r["values"][s] is not None for r in rows)
             else None for s in svc.source_ids()}
    costs = acquisition.cost_stats(rows)
    cost = costs["cost"]
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
            "value_by_source": value, "value": best, **costs,
            "value_by_kind": {k: sum(r["value"] for r in rows if r["price_kind"] == k)
                              for k in {r["price_kind"] for r in rows if r["value"] is not None}},
            "unpriced": sum(1 for r in rows if r["value"] is None),
            "needs_price": sum(1 for r in rows if r["needs_price"]),
            "no_data": sum(1 for r in rows if r["value"] is None and not r["needs_price"]),
            "ref_raw_value": sum(r["ref_raw_value"] or 0 for r in rows),
            "estimated": sum(1 for r in rows if r["estimated"]),
            "prices": await price_freshness(get_db())}


@router.post("/bulk-acquired")
async def bulk_acquired(body: BulkAcquiredIn):
    return await acquisition.bulk_apply(get_db(), body.ids, body.acquired.model_dump(mode="json", exclude_unset=True))


@router.patch("/{item_id}")
async def patch_item(item_id: str, body: CollectionPatch):
    db = get_db()
    oid = svc.oid(item_id)
    fields = body.model_dump(mode="json", exclude_unset=True)
    if "acquired" in fields and fields["acquired"] is None:
        raise HTTPException(422, "acquired cannot be null; send null fields to clear them")
    acq = fields.pop("acquired", None)
    if fields:
        fields["updated_at"] = datetime.now(timezone.utc)
        if not (await db.collection_items.update_one({"_id": oid}, {"$set": fields})).matched_count:
            raise HTTPException(404, "item not found")
        valuation_cache.bump()
    if acq:
        if await acquisition.apply_patch(db, oid, acq) is None:
            raise HTTPException(404, "item not found")
    return svc._out(await _get(db, oid))


async def _get(db, oid):
    it = await db.collection_items.find_one({"_id": oid})
    if not it:
        raise HTTPException(404, "item not found")
    return it


@router.get("/{item_id}/history")
async def item_history(item_id: str):
    db = get_db()
    await _get(db, svc.oid(item_id))
    return await acquisition.history(db, item_id)


@router.post("/{item_id}/history/{edit_id}/restore")
async def restore_edit(item_id: str, edit_id: str):
    it = await acquisition.restore(get_db(), svc.oid(item_id), edit_id)
    if it is None:
        raise HTTPException(404, "item or edit not found")
    return svc._out(it)


@router.post("/{item_id}/remove")
async def remove(item_id: str, body: RemoveIn):
    db = get_db()
    it = await db.collection_items.find_one({"_id": svc.oid(item_id)})
    if not it:
        raise HTTPException(404, "item not found")
    left = it["quantity"] - body.quantity
    if left <= 0:
        await db.collection_items.delete_one({"_id": it["_id"]})
        valuation_cache.bump()
        return {"deleted": True, "quantity": 0}
    await db.collection_items.update_one({"_id": it["_id"]}, {"$set": {"quantity": left}})
    valuation_cache.bump()
    return {"deleted": False, "quantity": left}


@router.delete("/{item_id}", status_code=204)
async def delete_item(item_id: str):
    r = await get_db().collection_items.delete_one({"_id": svc.oid(item_id)})
    valuation_cache.bump()
    if not r.deleted_count:
        raise HTTPException(404, "item not found")
