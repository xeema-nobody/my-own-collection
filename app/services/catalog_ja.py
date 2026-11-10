"""Japanese Pokémon catalog (decision D4, 2026-11-10): selected TCGdex `/ja` sets, on demand, catalog only.

Same `sets` / `cards` collections as English, `language: 'ja'`, ids `pokemon-ja:{set}-{num}` so nothing collides
with an English id. Idempotent (upserts on `_id`, known numbers are not fetched again). Never touches the collection.
"""
import logging

from app.db.mongo import get_db
from app.providers.catalog.tcgdex import CatalogIndex, TcgdexJaCatalog, id_prefix
from app.services import jobs, valuation_cache
from app.services.catalog_import import _without_raw

log = logging.getLogger(__name__)
PFX = id_prefix("ja")


async def ja_index(db) -> CatalogIndex:
    numbers: dict[str, set[str]] = {}
    async for c in db.cards.find({"tcg": "pokemon", "language": "ja"}, {"number": 1, "set.id": 1}):
        numbers.setdefault(c["set"]["id"], set()).add(c["number"])
    return CatalogIndex(numbers=numbers)


async def list_ja_sets(provider=None) -> list[dict]:
    """Upstream ja sets (one live request) with how many cards we hold: [{id, name, total, printed_total, imported}]."""
    db = get_db()
    provider = provider or TcgdexJaCatalog(await ja_index(db))
    held = {s["external_id"]: s async for s in db.sets.find({"language": "ja"}, {"external_id": 1, "imported_count": 1})}
    out = []
    for s in await provider.available_sets():
        cc = s.get("cardCount") or {}
        out.append({"id": s["id"], "name": s["name"], "total": cc.get("total"), "printed_total": cc.get("official") or None,
                    "imported": (held.get(s["id"]) or {}).get("imported_count", 0)})
    return out


async def import_ja_sets(set_ids: list[str], provider=None, trigger: str = "manual") -> dict:
    """Import the chosen ja sets in full (cards we lack only)."""
    db = get_db()
    provider = provider or TcgdexJaCatalog(await ja_index(db), wanted=set(set_ids))
    job = await jobs.start(db, "catalog_import", trigger)
    stats = {"sets": 0, "cards": 0, "set": set_ids[0] if len(set_ids) == 1 else None, "set_ids": set_ids,
             "origin": "selected", "language": "ja", "failed_sets": []}
    try:
        for s in await provider.list_sets():
            await db.sets.update_one({"_id": s["_id"]}, {"$set": s}, upsert=True)
            stats["sets"] += 1
        for sid in set_ids:
            try:
                async for card in provider.iter_cards(sid):
                    await db.cards.update_one({"_id": card["_id"]}, {"$set": _without_raw(card)}, upsert=True)
                    valuation_cache.bump()
                    stats["cards"] += 1
            except Exception as e:  # noqa: BLE001 - one set failing must not abort the rest
                log.warning("ja set %s failed: %s", sid, e)
                stats["failed_sets"].append(sid)
            count = await db.cards.count_documents({"tcg": "pokemon", "language": "ja", "set.id": sid})
            doc = await db.sets.find_one({"_id": f"{PFX}:{sid}"}) or {}
            expected = doc.get("total") or doc.get("printed_total")
            complete = expected is None or count >= expected
            await db.sets.update_one({"_id": f"{PFX}:{sid}"}, {"$set": {"imported_count": count, "complete": complete}})
            if not complete and sid not in stats["failed_sets"]:
                stats["failed_sets"].append(sid)
            await jobs.progress(db, job, stats)
        await jobs.finish(db, job, "partial" if stats["failed_sets"] else "ok", stats)
    except Exception as e:  # noqa: BLE001
        await jobs.finish(db, job, "error", stats, str(e))
        raise
    return stats
