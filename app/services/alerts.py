"""Price alerts: rules on a stack / card / collection total, evaluated after each price update.

Values come from `collection.valuate` (the same resolver the screens use); % rules compare it with
`valuate(as_of=now-days)` like `movers`. Money = integer base-currency cents.

State machine per rule: condition true while `triggered` is false -> one event, `triggered` true;
condition false -> re-armed. Condition unknown (unpriced, estimated, wrong kind, not comparable)
leaves the state alone. The flip is one atomic update, so repeated or concurrent runs never double-fire."""
import logging
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.db.models import AlertIn, AlertPatch
from app.services.collection import oid, valuate
from app.services.movers import comparable

log = logging.getLogger(__name__)

OP_TEXT = {"above": "above", "below": "below", "up_pct": "up", "down_pct": "down"}


def _fmt_cents(c: int) -> str:
    return f"{c / 100:,.2f}"


def describe(r: dict) -> str:
    target = {"total": "Collection total", "card": "Card", "stack": "Stack"}[r["scope"]]
    if r["scope"] != "total" and r.get("label"):
        target = f"{target} {r['label']}"
    if r["op"] in ("above", "below"):
        cond = f"{OP_TEXT[r['op']]} {_fmt_cents(int(r['threshold']))}"
    else:
        cond = f"{OP_TEXT[r['op']]} {r['threshold']:g}% over {r['days']} d"
    kind = "" if r["kind"] == "any" else f" ({r['kind']})"
    return f"{target} {cond}{kind}"


def _out(d: dict) -> dict:
    d = dict(d)
    d["id"] = str(d.pop("_id"))
    d["description"] = describe(d)
    return d


def _usable(v: dict, rule: dict) -> bool:
    return (v["value"] is not None and (rule["include_estimated"] or not v["estimated"])
            and (rule["kind"] == "any" or v["price_kind"] == rule["kind"]))


def _select(vals: list[dict], rule: dict) -> list[dict]:
    if rule["scope"] == "stack":
        return [v for v in vals if str(v["item"]["_id"]) == rule["item_id"]]
    if rule["scope"] == "card":
        return [v for v in vals if v["item"]["card_id"] == rule["card_id"]]
    return vals


def measure(rule: dict, vals: list[dict], past: dict | None) -> dict | None:
    """{value, prev, pct, rows} for the rule, or None when unknown (state must not change)."""
    rows = [v for v in _select(vals, rule) if _usable(v, rule)]
    if rule["op"] in ("above", "below"):
        if not rows:
            return None
        return {"value": sum(v["value"] for v in rows), "prev": None, "pct": None, "rows": rows}
    old = past or {}
    pairs = [(old[k], v) for v in rows if (k := v["item"]["_id"]) in old and comparable(old[k], v)]
    if not pairs:
        return None
    a, b = sum(o["value"] for o, _ in pairs), sum(n["value"] for _, n in pairs)
    return {"value": b, "prev": a, "pct": round((b - a) / a * 100, 2), "rows": [n for _, n in pairs]}


def condition_met(rule: dict, m: dict) -> bool:
    op, t = rule["op"], rule["threshold"]
    if op == "above":
        return m["value"] > t
    if op == "below":
        return m["value"] < t
    return m["pct"] >= t if op == "up_pct" else m["pct"] <= -t


def _event(rule: dict, m: dict, now: datetime) -> dict:
    rows = m["rows"]
    first = rows[0]
    card = first["card"] or {}
    return {"type": "alert", "rule_id": str(rule["_id"]), "rule": describe(rule),
            "card_id": first["item"]["card_id"] if rule["scope"] != "total" else None,
            "name": card.get("name") if rule["scope"] != "total" else "Collection total",
            "value": m["value"], "prev": m["prev"], "pct": m["pct"],
            "price_kind": first["price_kind"] if len(rows) == 1 else None,
            "match": first["match"] if len(rows) == 1 else None,
            "thin": any(v["thin"] for v in rows), "estimated": any(v["estimated"] for v in rows),
            "source": first["source"] if len(rows) == 1 else None, "fired_at": now, "read": False}


async def evaluate(db, vals: list[dict] | None = None) -> int:
    """Check every enabled rule; returns how many events were raised. Pass `vals` to reuse a valuation."""
    rules = await db.alerts.find({"enabled": True}).to_list(None)
    if not rules:
        return 0
    now = datetime.now(timezone.utc)
    vals = await valuate(db) if vals is None else vals
    pasts: dict[int, dict] = {}
    fired = 0
    for rule in rules:
        try:
            past = None
            if rule["op"] in ("up_pct", "down_pct"):
                d = rule["days"]
                if d not in pasts:
                    pasts[d] = {v["item"]["_id"]: v for v in await valuate(db, as_of=now - timedelta(days=d))}
                past = pasts[d]
            m = measure(rule, vals, past)
            if m is None:
                await db.alerts.update_one({"_id": rule["_id"]}, {"$set": {"last_eval": now}})
                continue
            met = condition_met(rule, m)
            upd = {"last_eval": now, "last_value": m["value"], "last_pct": m["pct"]}
            if not met:
                await db.alerts.update_one({"_id": rule["_id"]}, {"$set": {**upd, "triggered": False}})
                continue
            r = await db.alerts.update_one({"_id": rule["_id"], "triggered": False}, {"$set": {**upd, "triggered": True}})
            if r.modified_count == 1:
                await db.alert_events.insert_one(_event(rule, m, now))
                fired += 1
            else:
                await db.alerts.update_one({"_id": rule["_id"]}, {"$set": upd})
        except Exception:  # noqa: BLE001 - one broken rule must not stop the others
            log.exception("alert %s failed", rule.get("_id"))
    return fired


async def notify_system(db, key: str, text: str) -> bool:
    """Inbox item for an operational problem; `key` dedupes (e.g. 'fetch_skipped:2026-10-28')."""
    try:
        await db.alert_events.insert_one({"type": "system", "key": key, "rule": text, "name": None, "card_id": None,
                                          "fired_at": datetime.now(timezone.utc), "read": False})
    except DuplicateKeyError:
        return False
    return True


async def _label(db, body: AlertIn) -> tuple[str | None, str | None]:
    """(label, card_id) for the target; 404 when it does not exist."""
    if body.scope == "total":
        return None, None
    if body.scope == "stack":
        it = await db.collection_items.find_one({"_id": oid(body.item_id)})
        if not it:
            raise HTTPException(404, "stack not found")
        card_id = it["card_id"]
    else:
        card_id = body.card_id
        if not await db.collection_items.find_one({"card_id": card_id}):
            raise HTTPException(404, "card is not in the collection")
    card = await db.cards.find_one({"_id": card_id}, {"name": 1, "number": 1})
    name = f"{card['name']} #{card['number']}" if card else card_id
    if body.scope == "stack" and it.get("grading"):
        g = it["grading"]
        name += f" {g['company']} {g['grade']:g}"
    return name, card_id


async def create(db, body: AlertIn) -> dict:
    label, card_id = await _label(db, body)
    doc = {**body.model_dump(), "card_id": card_id, "label": label, "triggered": False, "last_value": None,
           "last_pct": None, "last_eval": None, "created_at": datetime.now(timezone.utc)}
    r = await db.alerts.insert_one(doc)
    return _out({**doc, "_id": r.inserted_id})


async def list_rules(db) -> list[dict]:
    return [_out(d) async for d in db.alerts.find().sort("created_at", -1)]


async def patch(db, id_: str, body: AlertPatch) -> dict:
    upd = body.model_dump(exclude_unset=True)
    if upd:
        # a changed rule starts armed so its new condition is judged fresh
        r = await db.alerts.update_one({"_id": oid(id_)}, {"$set": {**upd, "triggered": False}})
        if not r.matched_count:
            raise HTTPException(404, "alert not found")
    d = await db.alerts.find_one({"_id": oid(id_)})
    if not d:
        raise HTTPException(404, "alert not found")
    return _out(d)


async def delete(db, id_: str):
    r = await db.alerts.delete_one({"_id": oid(id_)})
    if not r.deleted_count:
        raise HTTPException(404, "alert not found")


def _event_out(d: dict) -> dict:
    d = dict(d)
    d["id"] = str(d.pop("_id"))
    d.pop("key", None)
    return d


async def events(db, unread: bool = False, limit: int = 100) -> list[dict]:
    flt = {"read": False} if unread else {}
    return [_event_out(d) async for d in db.alert_events.find(flt).sort("fired_at", -1).limit(limit)]


async def unread_count(db) -> int:
    return await db.alert_events.count_documents({"read": False})


async def mark_read(db, ids: list[str] | None = None) -> int:
    flt: dict = {"read": False}
    if ids is not None:
        flt["_id"] = {"$in": [ObjectId(i) for i in ids if ObjectId.is_valid(i)]}
    return (await db.alert_events.update_many(flt, {"$set": {"read": True}})).modified_count
