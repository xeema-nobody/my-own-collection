import logging

from pymongo import UpdateOne

from app.db.mongo import get_db
from app.providers.catalog.pokemontcg import PokemonTcgCatalog
from app.services import jobs
from app.services.sets import sets_with_stats
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
            if not await _record_completeness(db, sid) and sid not in stats["failed_sets"]:
                stats["failed_sets"].append(sid)  # upstream returned fewer cards than the set total, silently
            await jobs.progress(db, job, stats)
        stats["incomplete_sets"] = await _incomplete_ids(db, targets)
        if stats["incomplete_sets"]:
            log.warning("catalog health: %d incomplete set(s): %s", len(stats["incomplete_sets"]),
                        ", ".join(stats["incomplete_sets"]))
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


async def _record_completeness(db, sid: str) -> bool:
    """Store `imported_count` / `complete` on the set doc (imported vs upstream `total`); True when complete."""
    doc = await db.sets.find_one({"_id": f"pokemon:{sid}"}) or {}
    expected = doc.get("total") or doc.get("printed_total")
    count = await db.cards.count_documents({"tcg": "pokemon", "set.id": sid})
    complete = expected is None or count >= expected
    await db.sets.update_one({"_id": f"pokemon:{sid}"}, {"$set": {"imported_count": count, "complete": complete}})
    return complete


async def _incomplete_ids(db, only: list[str] | None = None) -> list[str]:
    """Sets with some cards imported but fewer than the upstream total (live counts, so old imports count too)."""
    return [s["external_id"] for s in await sets_with_stats(db)
            if s["cards_missing"] and (not only or s["external_id"] in only)]


async def incomplete_sets(db) -> list[str]:
    """What "Retry incomplete" re-imports: short sets plus sets that failed in the latest full import/retry."""
    ids = await _incomplete_ids(db)
    return ids + [s for s in await last_failed_sets(db) if s not in ids]


def _without_raw(card: dict) -> dict:
    return {k: v for k, v in card.items() if k != "_prices_raw"}
