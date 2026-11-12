"""Sealed products (boxes, ETBs, packs...): stacks of identical units with a manual market value.

Kept apart from cards: sealed value never feeds `collection.valuate` or a snapshot's `total_value`."""
from datetime import date, datetime, timezone

from fastapi import HTTPException

from app.db.models import ProductIn, ProductPatch
from app.services.collection import oid


def _out(p: dict) -> dict:
    d = {k: v for k, v in p.items() if k != "_id"}
    d["id"] = str(p["_id"])
    for k in ("purchase_date", "market_value_at", "sold_at"):   # stored as ISO strings
        d.setdefault(k, None)
    return d


def _iso(d: dict) -> dict:
    return {k: v.isoformat() if isinstance(v, date) else v for k, v in d.items()}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def create(db, body: ProductIn) -> dict:
    now = datetime.now(timezone.utc)
    doc = _iso(body.model_dump())
    doc["market_value_at"] = _today() if body.market_value is not None else None
    if body.status == "sold_sealed" and not doc.get("sold_at"):
        doc["sold_at"] = _today()
    doc.update(created_at=now, updated_at=now)
    r = await db.products.insert_one(doc)
    return _out({**doc, "_id": r.inserted_id})


async def list_(db, status: str | None = None, type_: str | None = None) -> list[dict]:
    flt = {k: v for k, v in (("status", status), ("type", type_)) if v}
    return [_out(p) async for p in db.products.find(flt).sort("created_at", -1)]


async def patch(db, id_: str, body: ProductPatch) -> dict:
    upd = _iso(body.model_dump(exclude_unset=True))
    for f in ("name", "type", "tcg", "language", "quantity", "status"):   # these cannot be cleared
        if f in upd and upd[f] is None:
            raise HTTPException(422, f"{f} cannot be empty")
    cur = await db.products.find_one({"_id": oid(id_)})
    if not cur:
        raise HTTPException(404, "product not found")
    if "market_value" in upd:
        upd["market_value_at"] = _today() if upd["market_value"] is not None else None
    if upd.get("status") == "sold_sealed" and not (upd.get("sold_at") or cur.get("sold_at")):
        upd["sold_at"] = _today()
    if upd:
        upd["updated_at"] = datetime.now(timezone.utc)
        await db.products.update_one({"_id": cur["_id"]}, {"$set": upd})
    return _out(await db.products.find_one({"_id": cur["_id"]}))


async def remove(db, id_: str) -> None:
    if not (await db.products.delete_one({"_id": oid(id_)})).deleted_count:
        raise HTTPException(404, "product not found")


async def summary(db) -> dict:
    """Sealed units only: opened / sold ones no longer count. Unknown value / cost is counted, never 0."""
    value = cost = units = unpriced = cost_missing = stacks = 0
    async for p in db.products.find({"status": "sealed"}):
        q = p["quantity"]
        stacks += 1
        units += q
        if p.get("market_value") is None:
            unpriced += 1
        else:
            value += p["market_value"] * q
        if p.get("purchase_price") is None:
            cost_missing += 1
        else:
            cost += p["purchase_price"] * q
    return {"value": value, "cost": cost, "stacks": stacks, "units": units,
            "unpriced": unpriced, "cost_missing": cost_missing}
