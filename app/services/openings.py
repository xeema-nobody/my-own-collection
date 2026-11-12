"""Opening a sealed product (roadmap Step 7 slice 2).

`open_product` takes units out of a sealed stack (a `collection_exits` row, reason "opened", cost snapshot kept),
stores one `openings` doc and optionally adds the pulled cards. The link product -> pulled cards lives on the
opening (`pulls`), not on the collection stack: pulled copies merge into existing stacks by stack_key.
D8: pulled cards carry no cost (acquisition 'pulled', price None) so they stay out of P/L but count in value.
Never auto-adds: every pull is an explicit request."""
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException

from app.config import settings
from app.db.models import CollectionIn, OpenIn, PullIn
from app.services import collection as coll
from app.services.pricing import get_rates


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


def _ratio(a: int | None, b: int | None) -> float | None:
    return None if a is None or not b else a / b


async def report(db) -> dict:
    """Opening ROI (roadmap Step 7 slice 3, decisions.md 'Opening result report'). Read-only.
    Pull value = today's market value of the pulled copies; unpriced pulls are counted, never valued 0."""
    ops = [o async for o in db.openings.find().sort("created_at", -1)]
    rates = await get_rates(db)
    box_ids = list({o["card_id"] for o in ops})
    boxes = {c["_id"]: c async for c in db.cards.find({"_id": {"$in": box_ids}}, {"language": 1, "name": 1})}
    pull_items, box_items = [], []
    for n, o in enumerate(ops):
        for i, p in enumerate(o["pulls"]):
            pull_items.append({"_id": f"{n}:{i}", "card_id": p["card_id"], "variant": p.get("variant"), "grading": None,
                               "language": p.get("language") or "en", "condition": p.get("condition"),
                               "quantity": p["quantity"], "_op": n})
        box_items.append({"_id": f"box:{n}", "card_id": o["card_id"], "variant": None, "grading": None,
                          "language": (boxes.get(o["card_id"]) or {}).get("language") or "en",
                          "condition": "NM", "quantity": o["quantity"], "acquired": o.get("acquired")})
    pv = await coll.valuate_items(db, pull_items) if pull_items else []
    bv = await coll.valuate_items(db, box_items) if box_items else []
    names = {c["_id"]: c.get("name") async for c in db.cards.find(
        {"_id": {"$in": list({p["card_id"] for o in ops for p in o["pulls"]})}}, {"name": 1})} if pull_items else {}
    thr = settings.opening_hit_threshold_cents
    rows = []
    for n, o in enumerate(ops):
        mine = [v for v in pv if v["item"]["_op"] == n]
        priced = [v for v in mine if v["value"] is not None]
        value = sum(v["value"] for v in priced) if priced else (0 if not mine else None)
        copies = sum(v["item"]["quantity"] for v in priced)
        hits = sum(v["item"]["quantity"] for v in priced if v["value"] / v["item"]["quantity"] >= thr)
        best = max(priced, key=lambda v: v["value"] / v["item"]["quantity"], default=None)
        cost, kept = bv[n]["cost"], bv[n]["value"]
        net = None if cost is None or value is None else value - cost
        rows.append({
            "id": str(o["_id"]), "card_id": o["card_id"], "name": o["name"], "date": o["date"], "units": o["quantity"],
            "cost": cost, "pulls_value": value, "net": net, "roi": _ratio(net, cost),
            "kept_value": kept, "vs_kept": None if kept is None or value is None else value - kept,
            "pulled_copies": sum(v["item"]["quantity"] for v in mine), "priced_copies": copies,
            "unpriced": sum(v["item"]["quantity"] for v in mine if v["value"] is None),
            "hits": hits, "hit_rate": _ratio(hits, copies) if copies else None,
            "best_hit": None if not best else {"card_id": best["item"]["card_id"], "name": names.get(best["item"]["card_id"]),
                                               "value": round(best["value"] / best["item"]["quantity"])}})
    prods: dict[str, dict] = {}

    def prod(cid: str, name) -> dict:
        return prods.setdefault(cid, {"card_id": cid, "name": name,
                                      "opened": {"units": 0, "cost": 0, "cost_unknown": 0, "pulls_value": 0, "net": None},
                                      "kept": {"units": 0, "value": 0, "cost": 0},
                                      "sold": {"units": 0, "proceeds": 0, "realised": 0}})
    for r in rows:
        o = prod(r["card_id"], r["name"])["opened"]
        o["units"] += r["units"]
        o["pulls_value"] += r["pulls_value"] or 0
        if r["cost"] is None:
            o["cost_unknown"] += r["units"]
        else:
            o["cost"] += r["cost"]
    for p in prods.values():
        o = p["opened"]
        o["net"] = None if o["cost_unknown"] else o["pulls_value"] - o["cost"]
    for v in await coll.valuate(db, kind="sealed"):
        p = prod(v["item"]["card_id"], (v["card"] or {}).get("name"))["kept"]
        p["units"] += v["item"]["quantity"]
        p["value"] += v["value"] or 0
        p["cost"] += v["cost"] or 0
    sealed_ids = [c["_id"] async for c in db.cards.find({"kind": "sealed"}, {"_id": 1})]
    async for e in db.collection_exits.find({"reason": "sold", "card_id": {"$in": sealed_ids}}):
        s = prod(e["card_id"], None)["sold"]
        r = rates.get(e.get("currency", "EUR"))
        s["units"] += e["quantity"]
        if e.get("price") is not None and r:
            s["proceeds"] += round((e["price"] * e["quantity"] - (e.get("fees") or 0) - (e.get("shipping_paid") or 0)) * r)
        if e.get("realised") is not None and r:
            s["realised"] += round(e["realised"] * r)
    missing = {c["_id"]: c.get("name") async for c in db.cards.find(
        {"_id": {"$in": [k for k, p in prods.items() if not p["name"]]}}, {"name": 1})}
    for k, nm in missing.items():
        prods[k]["name"] = nm
    known = [r for r in rows if r["cost"] is not None and r["net"] is not None]
    cost, pulls = sum(r["cost"] for r in known), sum(r["pulls_value"] for r in known)
    copies, hits = sum(r["priced_copies"] for r in rows), sum(r["hits"] for r in rows)
    vk = [r for r in rows if r["vs_kept"] is not None]
    return {"openings": rows, "products": sorted(prods.values(), key=lambda p: p["name"] or ""),
            "hit_threshold": thr,
            "totals": {"openings": len(rows), "units": sum(r["units"] for r in rows), "cost": cost if known else None,
                       "pulls_value": pulls if known else None, "net": pulls - cost if known else None,
                       "roi": _ratio(pulls - cost, cost) if known else None,
                       "hit_rate": _ratio(hits, copies) if copies else None,
                       "vs_kept": sum(r["vs_kept"] for r in vk) if vk else None,
                       "excluded_unknown_cost": len(rows) - len(known)}}
