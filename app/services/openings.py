"""Opening a sealed product (roadmap Step 7 slice 2).

`open_product` takes units out of a sealed stack (a `collection_exits` row, reason "opened", cost snapshot kept),
stores one `openings` doc and optionally adds the pulled cards. The link product -> pulled cards lives on the
opening (`pulls`), not on the collection stack: pulled copies merge into existing stacks by stack_key.
D8: pulled cards carry no cost (acquisition 'pulled', price None) so they stay out of P/L but count in value.
Never auto-adds: every pull is an explicit request."""
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException

from app.db.models import CollectionIn, OpenIn, PullIn
from app.services import collection as coll


def _oid(id_: str) -> ObjectId:
    try:
        return ObjectId(id_)
    except Exception:
        raise HTTPException(404, "opening not found")


def _out(d: dict) -> dict:
    d = dict(d)
    d["id"] = str(d.pop("_id"))
    d["created_at"] = d["created_at"].isoformat()
    return d


async def _check_pulls(db, pulled: list[PullIn]) -> None:
    """Unknown card = 404, a sealed entry = 400; called before anything is changed."""
    ids = {p.card_id for p in pulled}
    found = {c["_id"]: c async for c in db.cards.find({"_id": {"$in": list(ids)}}, {"kind": 1})}
    missing = sorted(ids - found.keys())
    if missing:
        raise HTTPException(404, f"card not found: {missing[0]}")
    if any(c.get("kind") == "sealed" for c in found.values()):
        raise HTTPException(400, "a sealed product is not a pulled card")


async def _add_pulls(db, opening: dict, pulled: list[PullIn]) -> list[dict]:
    """Add each pull as a 'pulled' stack and record it on the opening."""
    await _check_pulls(db, pulled)
    acquired = {"type": "pulled", "price": None, "currency": "EUR", "date": opening["date"],
                "source": f"opened: {opening['name']}"}
    out = []
    for p in pulled:
        r = await coll.add(db, CollectionIn(card_id=p.card_id, variant=p.variant, language=p.language,
                                            condition=p.condition, quantity=p.quantity, acquired=acquired))
        out.append({"card_id": p.card_id, "variant": p.variant, "language": p.language, "condition": p.condition,
                    "quantity": p.quantity, "stack_id": r["id"], "type_conflict": r.get("type_conflict", False)})
    if out:
        await db.openings.update_one({"_id": opening["_id"]}, {"$push": {"pulls": {"$each": [
            {k: v for k, v in o.items() if k != "type_conflict"} for o in out]}}})
    return out


async def open_product(db, item_id: str, body: OpenIn) -> dict:
    it = await db.collection_items.find_one({"_id": coll.oid(item_id)})
    if not it:
        raise HTTPException(404, "item not found")
    card = await db.cards.find_one({"_id": it["card_id"]}, {"kind": 1, "name": 1}) or {}
    if card.get("kind") != "sealed":
        raise HTTPException(400, "only a sealed product can be opened")
    await _check_pulls(db, body.pulled) if body.pulled else None
    qty = min(body.quantity, it["quantity"])
    now = datetime.now(timezone.utc)
    day = (body.date or now.date()).isoformat()
    op = {"_id": ObjectId(), "card_id": it["card_id"], "name": card.get("name") or it["card_id"], "quantity": qty,
          "date": day, "note": body.note, "extras": body.extras,
          "acquired": it.get("acquired"),  # cost snapshot of the opened units (informational, no allocation)
          "pulls": [], "created_at": now}
    await db.openings.insert_one(op)
    r = await coll.remove(db, item_id, quantity=qty, reason="opened", note=body.note,
                          date=body.date, opening_id=str(op["_id"]))
    pulled = await _add_pulls(db, op, body.pulled) if body.pulled else []
    return {"opening_id": str(op["_id"]), "opened": r["removed"], "left": r["quantity"], "stack_deleted": r["deleted"],
            "pulled": pulled}


async def add_pulls(db, opening_id: str, pulled: list[PullIn]) -> dict:
    op = await db.openings.find_one({"_id": _oid(opening_id)})
    if not op:
        raise HTTPException(404, "opening not found")
    return {"opening_id": opening_id, "pulled": await _add_pulls(db, op, pulled)}


async def get(db, opening_id: str) -> dict:
    op = await db.openings.find_one({"_id": _oid(opening_id)})
    if not op:
        raise HTTPException(404, "opening not found")
    return (await _list(db, [op]))[0]


async def list_openings(db, limit: int = 100) -> list[dict]:
    return await _list(db, [o async for o in db.openings.find().sort("created_at", -1).limit(limit)])


async def _list(db, ops: list[dict]) -> list[dict]:
    ids = {p["card_id"] for o in ops for p in o["pulls"]}
    cards = {c["_id"]: c async for c in db.cards.find({"_id": {"$in": list(ids)}}, {"name": 1, "number": 1, "set.name": 1})}
    out = []
    for o in ops:
        o = _out(o)
        o["pulls"] = [{**p, "name": (cards.get(p["card_id"]) or {}).get("name"),
                       "number": (cards.get(p["card_id"]) or {}).get("number"),
                       "set": ((cards.get(p["card_id"]) or {}).get("set") or {}).get("name")} for p in o["pulls"]]
        out.append(o)
    return out
