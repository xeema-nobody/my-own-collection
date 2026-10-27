import logging

from app.db.mongo import get_db
from app.providers.catalog.pokemontcg import PokemonTcgCatalog
from app.services import jobs
from app.services.pricing import get_rates, store_card_prices
from app.services.snapshots import take_snapshot

log = logging.getLogger(__name__)


async def refresh_prices(scope: str = "collection", sets: list[str] | None = None, provider=None) -> dict:
    """Re-fetch cards from the catalog API (prices ride along). Per-set batches.

    `sets` given: refresh every card of those sets (scope becomes `sets`).
    """
    db = get_db()
    provider = provider or PokemonTcgCatalog()
    scope = "sets" if sets else scope
    job = await jobs.start(db, "price_refresh")
    stats = {"scope": scope, "sets": sets, "cards": 0, "prices": 0, "errors": 0}
    try:
        rates = await get_rates(db)
        owned = await db.collection_items.distinct("card_id")
        owned_sets = set()
        for cid in owned:
            c = await db.cards.find_one({"_id": cid}, {"set.id": 1})
            if c:
                owned_sets.add(c["set"]["id"])
        if scope == "all":
            target_sets = {s["external_id"] async for s in db.sets.find({"tcg": "pokemon"})}
        elif scope == "sets":
            target_sets = set(sets)
        else:
            target_sets = owned_sets
        for sid in sorted(target_sets):
            try:
                async for card in provider.iter_cards(sid):
                    if scope == "collection" and card["_id"] not in owned:
                        continue
                    stats["prices"] += await store_card_prices(db, card, rates)
                    stats["cards"] += 1
            except Exception as e:  # noqa: BLE001 - one set failing must not abort the rest
                log.warning("refresh set %s failed: %s", sid, e)
                stats["errors"] += 1
        await take_snapshot(db)
        await jobs.finish(db, job, "ok" if not stats["errors"] else "partial", stats)
    except Exception as e:  # noqa: BLE001
        await jobs.finish(db, job, "error", stats, str(e))
        raise
    return stats
