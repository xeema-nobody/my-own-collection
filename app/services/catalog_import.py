import logging

from pymongo import UpdateOne

from app.db.mongo import get_db
from app.providers.catalog.pokemontcg import PokemonTcgCatalog
from app.services import jobs
from app.services.pricing import get_rates, store_card_prices

log = logging.getLogger(__name__)


async def import_catalog(set_ids: list[str] | None = None, provider=None, retry: bool = False,
                         trigger: str = "manual") -> dict:
    """Idempotent: upserts sets/cards by _id and records prices embedded in the payload.

    `set_ids=None` imports the full catalog. `stats.origin` (full | selected | retry) lets
    `last_failed_sets` find the run whose failures still need retrying.
    """
    db = get_db()
    provider = provider or PokemonTcgCatalog()
    job = await jobs.start(db, "catalog_import", trigger)
    stats = {"sets": 0, "cards": 0, "prices": 0, "set": set_ids[0] if set_ids and len(set_ids) == 1 else None,
             "set_ids": set_ids, "origin": "retry" if retry else "selected" if set_ids else "full"}
    try:
        sets = await provider.list_sets()
        ops = [UpdateOne({"_id": s["_id"]}, {"$set": s}, upsert=True)
               for s in sets]  # always keep the full set list for the filter UI
        if ops:
            await db.sets.bulk_write(ops, ordered=False)
        stats["sets"] = len(ops)
        rates = await get_rates(db)
        # Per-set batches: deep pagination on the upstream API is flaky, and one bad set
        # must not abort the rest.
        targets = set_ids or [s["external_id"] for s in sets]
        stats["failed_sets"] = []
        for sid in targets:
            try:
                async for card in provider.iter_cards(sid):
                    await db.cards.update_one({"_id": card["_id"]}, {"$set": _without_raw(card)}, upsert=True)
                    stats["prices"] += await store_card_prices(db, card, rates)
                    stats["cards"] += 1
            except Exception as e:  # noqa: BLE001
                log.warning("set %s failed: %s", sid, e)
                stats["failed_sets"].append(sid)
            await jobs.progress(db, job, stats)
        await jobs.finish(db, job, "partial" if stats["failed_sets"] else "ok", stats)
    except Exception as e:  # noqa: BLE001
        log.exception("catalog import failed")
        await jobs.finish(db, job, "error", stats, str(e))
        raise
    return stats


async def last_failed_sets(db) -> list[str]:
    """Failed set ids of the latest full-catalog import or retry (jobs before `origin` existed: set=None)."""
    job = await db.jobs.find_one({"type": "catalog_import", "status": {"$ne": "running"}, "$or": [
        {"stats.origin": {"$in": ["full", "retry"]}},
        {"stats.origin": {"$exists": False}, "stats.set": None}]}, sort=[("started_at", -1)])
    return list(((job or {}).get("stats") or {}).get("failed_sets") or [])


def _without_raw(card: dict) -> dict:
    return {k: v for k, v in card.items() if k != "_prices_raw"}
