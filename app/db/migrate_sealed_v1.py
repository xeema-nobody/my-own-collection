"""One-time, idempotent move of the slice-1 `products` collection (free-text set, hand-typed value) into the
sealed catalog model (services/sealed.py): each sealed product becomes a catalog entry + a normal stack.

- Set: matched by name against `sets`; a product whose set cannot be found stays in `products` (logged) and the
  collection is NOT renamed, so nothing is lost and the next boot retries.
- Cost (paid per unit, date, shop) and quantity carry over. The hand-typed market value is dropped: sealed value now
  comes from fetched prices (Cardmarket / PriceCharting).
- Opened / sold-sealed docs have no stack equivalent yet (openings come with the next slice); they stay in the backup.
- When every sealed product is moved, `products` is renamed `products_slice1_backup` (never dropped).
Runs on boot from init_indexes; a no-op once `products` is gone."""
import logging

from app.db.models import Acquired, SealedIn
from app.providers.catalog.common import norm
from app.services import sealed

log = logging.getLogger(__name__)
OLD, BACKUP = "products", "products_slice1_backup"


async def _find_set(db, name: str, language: str) -> dict | None:
    want = norm(name)
    if not want:
        return None
    lang = {"language": "ja"} if language == "ja" else {"language": {"$ne": "ja"}}
    rows = [s async for s in db.sets.find({"tcg": "pokemon", **lang})]
    return next((s for s in rows if norm(s["name"]) == want), None) or next(
        (s for s in rows if want in norm(s["name"]) or norm(s["name"]) in want), None)


async def migrate(db) -> dict:
    if OLD not in await db.list_collection_names():
        return {"moved": 0, "left": 0}
    moved = left = 0
    async for p in db[OLD].find({"status": "sealed", "migrated": {"$ne": True}}):
        s = await _find_set(db, p.get("set_name") or "", p.get("language", "en"))
        if not s:
            log.warning("sealed migration: no set matches %r for product %r, left in %s", p.get("set_name"), p.get("name"), OLD)
            left += 1
            continue
        acq = Acquired(type="purchased" if p.get("purchase_price") else None, price=p.get("purchase_price"),
                       date=p.get("purchase_date"), source=p.get("purchased_from"))
        try:
            await sealed.add(db, SealedIn(set_id=s["external_id"], type=p.get("type", "other"), language=p.get("language", "en"),
                                          quantity=p.get("quantity", 1), acquired=acq, notes=p.get("note")))
        except Exception:  # noqa: BLE001 - a bad doc must not block boot
            log.exception("sealed migration failed for product %r", p.get("name"))
            left += 1
            continue
        await db[OLD].update_one({"_id": p["_id"]}, {"$set": {"migrated": True}})
        moved += 1
    if not left and BACKUP not in await db.list_collection_names():
        await db[OLD].rename(BACKUP)
    return {"moved": moved, "left": left}
