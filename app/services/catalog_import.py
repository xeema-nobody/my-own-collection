import logging

from pymongo import UpdateOne

from app.db.mongo import get_db
from app.providers.catalog.pokemontcg import PokemonTcgCatalog
from app.services import jobs
from app.services.pricing import get_rates, store_card_prices

log = logging.getLogger(__name__)


async def import_catalog(set_id: str | None = None, provider=None) -> dict:
    """Idempotent: upserts sets/cards by _id and records prices embedded in the payload."""
    db = get_db()
    provider = provider or PokemonTcgCatalog()
    job = await jobs.start(db, "catalog_import")
    stats = {"sets": 0, "cards": 0, "prices": 0, "set": set_id}
    try:
        sets = await provider.list_sets()
        ops = [UpdateOne({"_id": s["_id"]}, {"$set": s}, upsert=True)
               for s in sets]  # always keep the full set list for the filter UI
        if ops:
            await db.sets.bulk_write(ops, ordered=False)
        stats["sets"] = len(ops)
        rates = await get_rates(db)
        async for card in provider.iter_cards(set_id):
            await db.cards.update_one({"_id": card["_id"]}, {"$set": _without_raw(card)}, upsert=True)
            stats["prices"] += await store_card_prices(db, card, rates)
            stats["cards"] += 1
            if stats["cards"] % 250 == 0:
                await jobs.progress(db, job, stats)
        await jobs.finish(db, job, "ok", stats)
    except Exception as e:  # noqa: BLE001
        log.exception("catalog import failed")
        await jobs.finish(db, job, "error", stats, str(e))
        raise
    return stats


def _without_raw(card: dict) -> dict:
    return {k: v for k, v in card.items() if k != "_prices_raw"}
