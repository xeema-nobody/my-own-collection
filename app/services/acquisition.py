"""Cost + acquisition type per stack: partial edits, weighted merge on add, edit log, P/L math.

Cost model: `acquired.price` is cents PER COPY, stack cost = price x quantity. Mixed costs in one stack
are held as the weighted average. Missing price = unknown (never 0); 0 = known free (pulled, gift).
"""
from datetime import datetime, timezone

from bson import ObjectId

from app.services import valuation_cache
from app.db.models import Acquired

TYPES = ("purchased", "pulled", "traded", "gift", "other")
FIELDS = ("type", "price", "currency", "date", "source")


def norm(a: dict | None) -> dict | None:
    """Stored acquired -> full canonical dict (missing `type` etc. = None), None stays None."""
    if a is None:
        return None
    return Acquired.model_validate(a).model_dump(mode="json")


def merge_acquired(old: dict | None, patch: dict) -> dict:
    """Apply a partial patch (only keys present) over the existing acquired doc."""
    cur = norm(old) or Acquired().model_dump(mode="json")
    return {**cur, **{k: v for k, v in patch.items() if k in FIELDS}}


def weighted_merge(old: dict | None, new: dict | None, qty_old: int, qty_new: int) -> tuple[dict | None, bool]:
    """Acquired of a stack after `qty_new` more copies join it. Returns (acquired, conflict)."""
    o, n = norm(old), norm(new)
    if n is None:
        return o, False
    if o is None:
        return n, False
    out, conflict = dict(o), False
    if o["type"] is None:
        out["type"] = n["type"]
    elif n["type"] is not None and n["type"] != o["type"]:
        conflict = True
    if o["price"] is None:
        out["price"], out["currency"] = n["price"], n["currency"]
    elif n["price"] is not None:
        if n["currency"] == o["currency"]:
            out["price"] = round((o["price"] * qty_old + n["price"] * qty_new) / (qty_old + qty_new))
        else:
            conflict = True  # cannot average across currencies: keep the old price
    for k in ("date", "source"):
        if o[k] is None:
            out[k] = n[k]
    return out, conflict


async def log_edit(db, item: dict, action: str, before: dict | None, after: dict | None) -> None:
    await db.collection_edits.insert_one({
        "item_id": str(item["_id"]), "stack_key": item.get("stack_key"), "card_id": item.get("card_id"),
        "at": datetime.now(timezone.utc), "action": action, "before": before, "after": after})


async def apply_patch(db, oid: ObjectId, patch: dict, action: str = "edit") -> dict | None:
    """Partial acquired edit; logged (previous value kept) only when something changed."""
    item = await db.collection_items.find_one({"_id": oid})
    if not item:
        return None
    before = norm(item.get("acquired"))
    after = merge_acquired(item.get("acquired"), patch)
    if after != before:
        await db.collection_items.update_one(
            {"_id": oid}, {"$set": {"acquired": after, "updated_at": datetime.now(timezone.utc)}})
        valuation_cache.bump()
        await log_edit(db, item, action, before, after)
    return await db.collection_items.find_one({"_id": oid})


async def bulk_apply(db, ids: list[str], patch: dict) -> dict:
    res = {"updated": 0, "unchanged": 0, "missing": []}
    for i in ids:
        try:
            oid = ObjectId(i)
        except Exception:  # noqa: BLE001 - bad id = not found
            res["missing"].append(i)
            continue
        item = await db.collection_items.find_one({"_id": oid}, {"acquired": 1})
        if item is None:
            res["missing"].append(i)
            continue
        changed = merge_acquired(item.get("acquired"), patch) != norm(item.get("acquired"))
        await apply_patch(db, oid, patch, "bulk")
        res["updated" if changed else "unchanged"] += 1
    return res


async def history(db, item_id: str, limit: int = 50) -> list[dict]:
    return [{**{k: v for k, v in e.items() if k != "_id"}, "id": str(e["_id"])}
            async for e in db.collection_edits.find({"item_id": item_id}).sort("at", -1).limit(limit)]


async def restore(db, oid: ObjectId, edit_id: str) -> dict | None:
    """Put the stack's acquired back to the `before` of a logged edit (itself logged)."""
    try:
        e = await db.collection_edits.find_one({"_id": ObjectId(edit_id), "item_id": str(oid)})
    except Exception:  # noqa: BLE001
        e = None
    item = await db.collection_items.find_one({"_id": oid})
    if not e or not item:
        return None
    cur = norm(item.get("acquired"))
    if cur != e["before"]:
        await db.collection_items.update_one(
            {"_id": oid}, {"$set": {"acquired": e["before"], "updated_at": datetime.now(timezone.utc)}})
        valuation_cache.bump()
        await log_edit(db, item, "restore", cur, e["before"])
    return await db.collection_items.find_one({"_id": oid})


def cost_stats(rows: list[dict]) -> dict:
    """P/L only over stacks with a known cost AND a value, so a stack with no cost never counts as
    cost 0. `rows` = `valuate` output. Pulled stacks are split out ("P/L excl. pulled")."""
    def typ(r):
        return ((r["item"].get("acquired") or {}).get("type")) or "unset"
    basis = [r for r in rows if r["cost"] is not None and r["value"] is not None]
    nopull = [r for r in basis if typ(r) != "pulled"]
    pl = lambda rs: sum(r["value"] - r["cost"] for r in rs) if rs else None  # noqa: E731
    by_type: dict[str, dict] = {}
    for r in rows:
        b = by_type.setdefault(typ(r), {"stacks": 0, "cards": 0, "cost": 0, "value": 0})
        b["stacks"] += 1
        b["cards"] += r["item"]["quantity"]
        b["cost"] += r["cost"] or 0
        b["value"] += r["value"] or 0
    return {
        "cost": sum(r["cost"] or 0 for r in rows),
        "cost_ex_pulled": sum(r["cost"] or 0 for r in rows if typ(r) != "pulled"),
        "cost_basis_cost": sum(r["cost"] for r in basis), "cost_basis_value": sum(r["value"] for r in basis),
        "cost_basis_cost_ex_pulled": sum(r["cost"] for r in nopull),
        "pl": pl(basis), "pl_ex_pulled": pl(nopull),
        "pulled_value": sum(r["value"] or 0 for r in rows if typ(r) == "pulled"),
        "cost_missing": sum(1 for r in rows if r["cost"] is None),
        "by_type": by_type,
    }
