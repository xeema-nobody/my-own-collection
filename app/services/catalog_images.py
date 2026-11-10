"""Move stored card images off images.pokemontcg.io onto TCGdex assets (decision D6, 2026-11-10).

Reversible and idempotent: the old `images` dict is kept once in `images_legacy`, a card with no TCGdex artwork keeps
its old URL, a card already on another host is not touched. Only the provider talks to the network.
"""
import logging

from app.db.mongo import get_db
from app.services import jobs, valuation_cache

log = logging.getLogger(__name__)
LEGACY_HOST = "images.pokemontcg.io"
_ON_LEGACY = {"tcg": "pokemon", "language": {"$ne": "ja"}, "images.small": {"$regex": f"//{LEGACY_HOST}/"}}


async def status(db=None) -> dict:
    """How many English cards still point at the old host, the top sets, and how many can be restored."""
    db = get_db() if db is None else db
    top = await db.cards.aggregate([{"$match": _ON_LEGACY}, {"$group": {"_id": "$set.id", "n": {"$sum": 1}}},
                                    {"$sort": {"n": -1}}, {"$limit": 10}]).to_list(10)
    return {"legacy": await db.cards.count_documents(_ON_LEGACY),
            "restorable": await db.cards.count_documents({"images_legacy": {"$exists": True}}),
            "top_sets": [{"set": t["_id"], "cards": t["n"]} for t in top]}


async def repoint_images(provider=None, sets: list[str] | None = None, trigger: str = "manual") -> dict:
    db = get_db()
    if provider is None:
        from app.services.catalog_provider import get_catalog
        provider = await get_catalog()
    if not hasattr(provider, "set_images"):
        raise ValueError("the configured catalog provider has no image listing (use CATALOG_PROVIDER=tcgdex)")
    job = await jobs.start(db, "catalog_images", trigger)
    stats = {"sets": 0, "repointed": 0, "no_image": 0, "no_counterpart": [], "failed_sets": []}
    try:
        todo = sets or sorted(await db.cards.distinct("set.id", _ON_LEGACY))
        for sid in todo:
            try:
                images = await provider.set_images(sid)
                if not images:
                    stats["no_counterpart"].append(sid)
                async for c in db.cards.find({**_ON_LEGACY, "set.id": sid}, {"number": 1, "images": 1, "images_legacy": 1}):
                    new = images.get(c["number"])
                    if not new:
                        stats["no_image"] += 1
                        continue
                    upd = {"images": new}
                    if "images_legacy" not in c:
                        upd["images_legacy"] = c["images"]
                    await db.cards.update_one({"_id": c["_id"]}, {"$set": upd})
                    stats["repointed"] += 1
            except Exception as e:  # noqa: BLE001 - one set failing must not abort the rest
                log.warning("images of set %s failed: %s", sid, e)
                stats["failed_sets"].append(sid)
            stats["sets"] += 1
            await jobs.progress(db, job, stats)
        valuation_cache.bump()
        await jobs.finish(db, job, "partial" if stats["failed_sets"] else "ok", stats)
    except Exception as e:  # noqa: BLE001
        await jobs.finish(db, job, "error", stats, str(e))
        raise
    return stats


async def restore_images(db=None) -> int:
    """Put the saved pokemontcg.io URLs back (rollback)."""
    db = get_db() if db is None else db
    n = 0
    async for c in db.cards.find({"images_legacy": {"$exists": True}}, {"images_legacy": 1}):
        await db.cards.update_one({"_id": c["_id"]}, {"$set": {"images": c["images_legacy"]}, "$unset": {"images_legacy": ""}})
        n += 1
    valuation_cache.bump()
    return n
