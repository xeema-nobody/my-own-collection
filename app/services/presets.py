"""Saved filter presets for the Collection / Wishlist lists (stored in Mongo so they follow the
user across browsers and devices). The built-in presets live in the frontend."""
from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.db.models import PresetIn
from app.services.collection import oid

# URL params a list page may save (filters, sort, view); anything else is rejected, not stored
ALLOWED = {"q", "tcg", "set", "rarity", "type", "language", "condition", "graded", "grader", "grade",
           "acquisition", "sale", "platform", "has_photos", "cost_missing", "needs_price", "stale", "price_min", "price_max", "pl",
           "sort", "order", "size", "filter", "view"}
MAX_PRESETS = 50


def _out(d: dict) -> dict:
    return {"id": str(d["_id"]), "name": d["name"], "scope": d["scope"], "query": d["query"]}


async def list_(db, scope: str) -> list[dict]:
    return [_out(d) async for d in db.list_presets.find({"scope": scope}).sort("name", 1)]


async def create(db, body: PresetIn) -> dict:
    bad = sorted(set(body.query) - ALLOWED)
    if bad:
        raise HTTPException(422, f"unknown filter(s): {', '.join(bad)}")
    if any(len(v) > 200 for v in body.query.values()):
        raise HTTPException(422, "filter value too long")
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "name required")
    if await db.list_presets.count_documents({"scope": body.scope}) >= MAX_PRESETS \
            and not await db.list_presets.find_one({"scope": body.scope, "name": name}):
        raise HTTPException(422, f"at most {MAX_PRESETS} presets")
    # same name replaces (save-over); `page` is never part of a preset
    await db.list_presets.update_one(
        {"scope": body.scope, "name": name},
        {"$set": {"query": body.query}, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}}, upsert=True)
    return _out(await db.list_presets.find_one({"scope": body.scope, "name": name}))


async def remove(db, id_: str) -> None:
    if not (await db.list_presets.delete_one({"_id": oid(id_)})).deleted_count:
        raise HTTPException(404, "preset not found")
