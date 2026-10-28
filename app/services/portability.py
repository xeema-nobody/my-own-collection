"""Collection export / import (JSON lossless, CSV for spreadsheets). Import upserts on `stack_key`."""
import csv
import io
import json
from datetime import datetime, timezone

from pydantic import ValidationError

from app.db.models import CollectionIn
from app.services.collection import stack_key

FORMAT, VERSION = "moc-collection", 1
MAX_ROWS = 20000
# `name`, `set`, `number` are for humans reading the sheet; import ignores them.
CSV_COLUMNS = ["card_id", "name", "set", "number", "variant", "language", "condition",
               "grade_company", "grade", "cert_number", "quantity", "acquired_price",
               "acquired_currency", "acquired_date", "acquired_source", "notes", "tags"]


def _item_row(d: dict) -> dict:
    """Stored item -> CollectionIn-shaped dict (no ids, no stack_key)."""
    row = {k: d.get(k) for k in ("card_id", "variant", "language", "condition", "grading",
                                 "quantity", "acquired", "notes")}
    row["tags"] = d.get("tags") or []
    row["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
    return row


async def export_items(db) -> list[dict]:
    return [_item_row(d) async for d in db.collection_items.find().sort("created_at", 1)]


def to_json(items: list[dict]) -> str:
    return json.dumps({"format": FORMAT, "version": VERSION,
                       "exported_at": datetime.now(timezone.utc).isoformat(), "items": items},
                      ensure_ascii=False, indent=1)


async def to_csv(db, items: list[dict]) -> str:
    ids = list({i["card_id"] for i in items})
    cards = {c["_id"]: c async for c in db.cards.find({"_id": {"$in": ids}},
                                                        {"name": 1, "set.name": 1, "number": 1})}
    out = io.StringIO()
    w = csv.DictWriter(out, CSV_COLUMNS, lineterminator="\n")
    w.writeheader()
    for i in items:
        c, g, a = cards.get(i["card_id"], {}), i["grading"] or {}, i["acquired"] or {}
        w.writerow({
            "card_id": i["card_id"], "name": c.get("name"), "set": (c.get("set") or {}).get("name"),
            "number": c.get("number"), "variant": i["variant"], "language": i["language"],
            "condition": i["condition"], "grade_company": g.get("company"), "grade": g.get("grade"),
            "cert_number": g.get("cert_number"), "quantity": i["quantity"],
            "acquired_price": a.get("price"), "acquired_currency": a.get("currency"),
            "acquired_date": a.get("date"), "acquired_source": a.get("source"),
            "notes": i["notes"], "tags": ";".join(i["tags"])})
    return out.getvalue()


def _csv_row(r: dict) -> dict:
    v = {k: (val.strip() if isinstance(val, str) else val) or None for k, val in r.items()}
    row = {"card_id": v.get("card_id"), "variant": v.get("variant"),
           "language": v.get("language") or "en", "condition": v.get("condition"),
           "quantity": v.get("quantity") or 1, "notes": r.get("notes") or None,
           "tags": [t.strip() for t in (v.get("tags") or "").split(";") if t.strip()]}
    if v.get("grade_company") or v.get("grade"):
        row["grading"] = {"company": v.get("grade_company"), "grade": v.get("grade"),
                          "cert_number": v.get("cert_number")}
    if any(v.get(k) for k in ("acquired_price", "acquired_date", "acquired_source")):
        a = {"price": v.get("acquired_price"), "date": v.get("acquired_date"),
             "source": v.get("acquired_source")}
        if v.get("acquired_currency"):
            a["currency"] = v["acquired_currency"]
        row["acquired"] = a
    return row


def parse(raw: bytes, fmt: str) -> list[dict]:
    """Bytes -> list of row dicts. Raises ValueError on a malformed file."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ValueError("file is not UTF-8") from e
    if fmt == "csv":
        rows = [_csv_row(r) for r in csv.DictReader(io.StringIO(text))]
    else:
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON: {e}") from e
        if not isinstance(doc, dict) or doc.get("format") != FORMAT:
            raise ValueError("not a moc-collection export")
        if doc.get("version") != VERSION:
            raise ValueError(f"unsupported export version {doc.get('version')}")
        rows = doc.get("items")
        if not isinstance(rows, list):
            raise ValueError("`items` must be a list")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"too many rows (max {MAX_ROWS})")
    return rows


async def import_items(db, rows: list[dict], mode: str = "set") -> dict:
    """`set`: quantity is overwritten, so re-importing a file is a no-op. `add`: quantity is added."""
    res = {"created": 0, "updated": 0, "errors": []}
    now = datetime.now(timezone.utc)
    known = {c["_id"] async for c in db.cards.find(
        {"_id": {"$in": list({r["card_id"] for r in rows if isinstance(r, dict)
                              and isinstance(r.get("card_id"), str)})}}, {"_id": 1})}
    for n, r in enumerate(rows, 1):
        try:
            if not isinstance(r, dict):
                raise ValueError("row is not an object")
            created = r.get("created_at")
            item = CollectionIn.model_validate({k: v for k, v in r.items() if k != "created_at"})
            if item.card_id not in known:
                raise ValueError(f"card not found: {item.card_id}")
            if created is not None and not isinstance(created, str):
                raise ValueError("created_at must be an ISO date string")
            created = datetime.fromisoformat(created) if created else now
        except (ValidationError, ValueError) as e:
            msg = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()) \
                if isinstance(e, ValidationError) else str(e)
            res["errors"].append({"row": n, "error": msg})
            continue
        key = stack_key(item)
        doc = item.model_dump(mode="json", exclude={"quantity"})
        edit = ("acquired", "notes", "tags")  # mutable fields: a `set` import restores them too
        on_insert = {k: v for k, v in doc.items() if mode == "set" and k not in edit or mode == "add"}
        upd = {"$setOnInsert": {**on_insert, "stack_key": key, "created_at": created},
               "$set": {"updated_at": now}}
        if mode == "add":
            upd["$inc"] = {"quantity": item.quantity}
        else:
            upd["$set"].update({"quantity": item.quantity, **{k: doc[k] for k in edit}})
        out = await db.collection_items.update_one({"stack_key": key}, upd, upsert=True)
        res["created" if out.upserted_id else "updated"] += 1
    return res
