"""Sealed products (boxes, ETBs, packs...). No catalog API lists them, so the user defines one (set from our sets +
type + language [+ edition]) and the app keeps it as a catalog entry in `cards` with `kind: "sealed"`.

Owning one is a normal collection stack on that entry, so prices (scraped sources), photos, sale status, the
Vinted publish queue, reprice and alerts all work unchanged. What differs:
- `set.id` is `sealed:<set id>`, so every per-set query over real cards (counts, imports, scans) skips them;
  the real id is kept in `set.ref_id`.
- `collection.valuate` keeps sealed rows out of every card total (`kind="cards"` default); `summary` reports them apart.
- Stacks use condition NM internally (a sealed product is mint); the UI and listing text show 'Sealed'."""
import re
from datetime import datetime, timezone

from fastapi import HTTPException

from app.db.models import CollectionIn, SealedIn
from app.providers.catalog.common import norm
from app.services import collection as coll
from app.services.pricing import PRICE_SCHEMA

TYPES: dict[str, str] = {
    "booster_box": "Booster Box", "booster_bundle": "Booster Bundle", "etb": "Elite Trainer Box",
    "booster_pack": "Booster Pack", "tin": "Tin", "collection_box": "Collection Box", "blister": "Blister",
    "other": "Sealed Product"}
SEALED_CONDITION = "NM"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(s)).strip("-")


def entry_id(set_id: str, type_: str, language: str, edition: str | None) -> str:
    return ":".join(["sealed", "pokemon", language, set_id, type_] + ([_slug(edition)] if edition and _slug(edition) else []))


def entry_name(set_name: str, type_: str, edition: str | None) -> str:
    return f"{set_name} {TYPES[type_]}" + (f" ({edition.strip()})" if edition and edition.strip() else "")


async def _set(db, set_id: str, language: str) -> dict:
    flt = {"tcg": "pokemon", "external_id": set_id, "language": "ja" if language == "ja" else {"$ne": "ja"}}
    s = await db.sets.find_one(flt)
    if not s:
        raise HTTPException(404, "set not found: pick one from the sets list")
    return s


async def ensure_entry(db, body: SealedIn) -> dict:
    """The catalog entry for this product; created once, never overwritten (prices live on it)."""
    s = await _set(db, body.set_id, body.language)
    edition = (body.edition or "").strip() or None
    cid = entry_id(body.set_id, body.type, body.language, edition)
    name = entry_name(s["name"], body.type, edition)
    logo = s.get("logo_url")
    doc = {
        "_id": cid, "kind": "sealed", "tcg": "pokemon", "external_id": cid.split(":", 2)[2],
        "sealed_type": body.type, "edition": edition, "name": name, "name_norm": norm(name), "number": "",
        "number_sort": 0, "supertype": "Sealed", "subtypes": [], "types": [], "rarity": TYPES[body.type],
        "set": {"id": f"sealed:{body.set_id}", "ref_id": body.set_id, "name": s["name"], "series": s.get("series"),
                "release_date": s.get("release_date"), "printed_total": None, "total": None,
                "ptcgo_code": s.get("ptcgo_code"), "logo_url": logo, "symbol_url": s.get("symbol_url")},
        "images": {"small": logo, "large": logo} if logo else {}, "variants": [], "language": body.language,
        "price_schema": PRICE_SCHEMA,   # without it the boot-time v2 price migration re-nests scraped prices

        "external_ids": {"tcgplayer_url": None, "cardmarket_url": None},
        "search_text": norm(" ".join(filter(None, [name, s["name"], TYPES[body.type], edition, "sealed"]))),
        "updated_at": datetime.now(timezone.utc)}
    await db.cards.update_one({"_id": cid}, {"$setOnInsert": doc}, upsert=True)
    return await db.cards.find_one({"_id": cid}, {"raw": 0})


async def add(db, body: SealedIn) -> dict:
    """Define-or-find the product, then add the stack. Returns the stack plus its catalog entry."""
    entry = await ensure_entry(db, body)
    stack = await coll.add(db, CollectionIn(card_id=entry["_id"], language=body.language, condition=SEALED_CONDITION,
                                            quantity=body.quantity, acquired=body.acquired, notes=body.notes))
    return {**stack, "entry": {k: entry.get(k) for k in ("_id", "name", "sealed_type", "edition", "set", "language")}}


async def list_entries(db, q: str | None = None, set_id: str | None = None, limit: int = 100) -> list[dict]:
    """Known sealed catalog entries (every product ever added), newest set first."""
    flt: dict = {"kind": "sealed"}
    if set_id:
        flt["set.ref_id"] = set_id
    for tok in norm(q or "").split():
        flt.setdefault("$and", []).append({"search_text": {"$regex": re.escape(tok)}})
    cur = db.cards.find(flt, {"raw": 0}).sort([("set.release_date", -1), ("name_norm", 1)]).limit(limit)
    return [{**{k: c.get(k) for k in ("name", "sealed_type", "edition", "set", "language", "images")}, "id": c["_id"]}
            async for c in cur]


async def summary(db) -> dict:
    """Sealed stacks only. value = sum of priced stacks; unpriced stacks are counted, never valued at 0."""
    rows = await coll.valuate(db, kind="sealed")
    return {"stacks": len(rows), "units": sum(r["item"]["quantity"] for r in rows),
            "value": sum(r["value"] or 0 for r in rows), "cost": sum(r["cost"] or 0 for r in rows),
            "unpriced": sum(1 for r in rows if r["value"] is None),
            "cost_missing": sum(1 for r in rows if r["cost"] is None)}
