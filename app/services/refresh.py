import logging

from app.config import settings
from app.db.mongo import get_db
from app.services.catalog_provider import get_catalog, get_ja_catalog
from app.services import jobs
from app.services.pricing import get_rates, store_card_prices, tracked_card_ids
from app.services.snapshots import take_snapshot

log = logging.getLogger(__name__)
SCOPES = ("tracked", "collection", "wishlist")   # all of them write only tracked cards


async def refresh_prices(scope: str = "tracked", sets: list[str] | None = None, provider=None, trigger: str = "manual") -> dict:
    """Re-fetch TRACKED cards (collection + wishlist) from the catalog API (prices ride along). Per-set batches.

    scope: tracked (both), collection, wishlist. `sets` narrows the run to the tracked cards of those sets.
    Untracked cards are never written (price scope, docs/pricing.md)."""
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}")
    db = get_db()
    provider = provider or await get_catalog()
    job = await jobs.start(db, "price_refresh", trigger)
    stats = {"scope": scope, "sets": sets, "cards": 0, "prices": 0, "errors": 0}
    try:
        rates = await get_rates(db)
        want: set[str] = set()
        if scope in ("tracked", "collection"):
            want |= set(await db.collection_items.distinct("card_id"))
        if scope in ("tracked", "wishlist"):
            want |= set(await db.wishlist.distinct("card_id"))
        by_set: dict[tuple[str, str], set[str]] = {}   # (language, set id): ja set codes may repeat English ones
        async for c in db.cards.find({"_id": {"$in": sorted(want)}}, {"set.id": 1, "language": 1}):
            by_set.setdefault((c.get("language") or "en", c["set"]["id"]), set()).add(c["_id"])
        ja = None
        for key in sorted(k for k in by_set if not sets or k[1] in sets):
            lang, sid = key
            ids = by_set[key]
            try:
                if lang == "ja":   # Japanese cards always come from TCGdex /ja, whatever CATALOG_PROVIDER says
                    ja = ja or await get_ja_catalog()
                prov = ja if lang == "ja" else provider
                async for card in prov.iter_cards(sid, only=ids):
                    if card["_id"] not in ids:
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


async def price_new_tracked(card_id: str) -> None:
    """Background, best effort: a card that just became tracked and has no catalog price yet gets one fetch.

    Never raises (adding to the collection must not depend on the price API)."""
    if not settings.price_on_add:
        return
    try:
        db = get_db()
        card = await db.cards.find_one({"_id": card_id}, {"latest_price": 1})
        if card and not card.get("latest_price"):
            await refresh_card_price(db, card_id)
    except Exception as e:  # noqa: BLE001
        log.warning("price on add failed for %s: %s", card_id, e)


async def refresh_card_price(db, card_id: str, provider=None) -> dict:
    """One-card catalog price fetch (a user action: card opened / just added). Stores that card's prices only.

    Not a job (small, synchronous). Returns {"found", "prices", "tracked"}; raises LookupError for an unknown card."""
    card = await db.cards.find_one({"_id": card_id}, {"set.id": 1, "language": 1})
    if not card:
        raise LookupError(card_id)
    provider = provider or (await get_ja_catalog() if card.get("language") == "ja" else await get_catalog())
    rates = await get_rates(db)
    out = {"found": False, "prices": 0, "tracked": card_id in await tracked_card_ids(db)}
    async for c in provider.iter_cards(card["set"]["id"], only={card_id}):
        if c["_id"] == card_id:
            out["found"], out["prices"] = True, await store_card_prices(db, c, rates)
            break
    return out
