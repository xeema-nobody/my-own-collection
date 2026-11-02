"""Wishlist: cards you want (raw, or a given grade) with an optional target price.

Priced like one owned copy (`collection.valuate_wishlist`). A target price keeps one linked
"below target" alert rule (`auto` flag) in sync, so the alert engine does the notifying."""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.db.models import AlertIn, WishIn, WishPatch
from app.services import alerts
from app.services.collection import oid, valuate_wishlist

PRICE_FIELDS = ("value", "estimated", "price_kind", "source", "match", "thin", "stale", "needs_price", "as_of")


def make_wish_key(card_id: str, variant: str | None, grading) -> str:
    """`grading` is a Grading model, a stored dict or None."""
    g = grading.model_dump() if hasattr(grading, "model_dump") else grading
    return "|".join(map(str, [card_id, variant or "", g["company"] if g else "", g["grade"] if g else ""]))


def _out(w: dict, v: dict | None = None) -> dict:
    d = {k: val for k, val in w.items() if k not in ("_id", "wish_key")}
    d["id"] = str(w["_id"])
    if v is not None:
        c = v["card"] or {}
        d["card"] = {k: c.get(k) for k in ("_id", "name", "number", "rarity", "set", "images")} if c else None
        d.update({k: v[k] for k in PRICE_FIELDS})
        t = w.get("target_price")
        d["gap"] = None if v["value"] is None or t is None else v["value"] - t
        d["hit"] = d["gap"] is not None and d["gap"] <= 0
    return d


async def _auto_rule(db, wish_id: str) -> dict | None:
    return await db.alerts.find_one({"wish_id": wish_id, "auto": True})


async def sync_alert(db, w: dict) -> None:
    """Make the linked rule match the entry: present iff `alert` and `target_price`."""
    wid = str(w["_id"])
    rule = await _auto_rule(db, wid)
    want = bool(w.get("alert", True) and w.get("target_price"))
    if not want:
        if rule:
            await db.alerts.delete_one({"_id": rule["_id"]})
    elif not rule:
        r = await alerts.create(db, AlertIn(scope="wish", wish_id=wid, op="below", threshold=w["target_price"]))
        await db.alerts.update_one({"_id": oid(r["id"])}, {"$set": {"auto": True}})
    elif rule["threshold"] != w["target_price"]:
        await db.alerts.update_one({"_id": rule["_id"]}, {"$set": {"threshold": w["target_price"], "triggered": False}})


async def add(db, body: WishIn) -> dict:
    """Upsert on (card, variant, grade): adding again updates target / note."""
    if not await db.cards.find_one({"_id": body.card_id}, {"_id": 1}):
        raise HTTPException(404, "card not found")
    key = make_wish_key(body.card_id, body.variant, body.grading)
    now = datetime.now(timezone.utc)
    sets = {"updated_at": now, "alert": body.alert}
    for f in ("target_price", "note"):
        if f in body.model_fields_set:
            sets[f] = getattr(body, f)
    await db.wishlist.update_one(
        {"wish_key": key},
        {"$set": sets, "$setOnInsert": {"wish_key": key, "card_id": body.card_id, "variant": body.variant,
                                        "grading": body.grading.model_dump() if body.grading else None,
                                        "created_at": now}},
        upsert=True)
    w = await db.wishlist.find_one({"wish_key": key})
    await sync_alert(db, w)
    return await _one(db, w)


async def _one(db, w: dict) -> dict:
    return next(e for e in await list_(db, w["card_id"]) if e["id"] == str(w["_id"]))


async def list_(db, card_id: str | None = None) -> list[dict]:
    vals = {v["item"]["_id"]: v for v in await valuate_wishlist(db)}
    flt = {"card_id": card_id} if card_id else {}
    return [_out(w, vals.get(w["_id"])) async for w in db.wishlist.find(flt).sort("created_at", -1)]


async def patch(db, id_: str, body: WishPatch) -> dict:
    upd = body.model_dump(exclude_unset=True)
    if upd:
        upd["updated_at"] = datetime.now(timezone.utc)
        r = await db.wishlist.update_one({"_id": oid(id_)}, {"$set": upd})
        if not r.matched_count:
            raise HTTPException(404, "wishlist entry not found")
    w = await db.wishlist.find_one({"_id": oid(id_)})
    if not w:
        raise HTTPException(404, "wishlist entry not found")
    await sync_alert(db, w)
    return await _one(db, w)


async def remove(db, id_: str) -> None:
    r = await db.wishlist.delete_one({"_id": oid(id_)})
    if not r.deleted_count:
        raise HTTPException(404, "wishlist entry not found")
    await db.alerts.delete_many({"scope": "wish", "wish_id": id_})   # rules of a gone entry would never evaluate
