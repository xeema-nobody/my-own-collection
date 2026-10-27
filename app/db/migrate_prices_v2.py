"""Idempotent migration to price model v2 (see docs/pricing.md). Runs on boot from init_indexes.

- prices: add `observed_on` (UTC date of *our* fetch, from fetched_at; not upstream as_of), cardmarket
  variant 'default' -> None, drop rows that collapse onto the same key (newest as_of wins), 0 -> None.
- cards: latest_price re-nested as [source][kind][grade][variant], `variants` placeholder ["normal"]
  -> [] when the card has no TCGplayer data, price_base recomputed (0 -> None), price_schema=2.
- collection_items: variant "normal" on a variantless card -> None, stack_key rebuilt (stacks that
  now collide are merged).
Re-running is a no-op once everything carries observed_on / price_schema=2.
"""
import logging
from datetime import datetime, timezone

from pymongo import UpdateOne
from pymongo.errors import DuplicateKeyError

from app.config import settings
from app.services.pricing import NO_VARIANT, PRICE_SCHEMA, best_base, today

log = logging.getLogger(__name__)

OLD_INDEX = "card_id_1_variant_1_source_1_kind_1_grade_key_1_as_of_1"
PRICE_FIELDS = ("low", "avg", "mid", "high", "market", "trend", "avg7", "avg30")
BATCH = 1000


def _day(*candidates) -> str:
    for d in candidates:
        if isinstance(d, datetime):
            return d.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return today()


async def _cached_rates(db) -> dict:
    """Newest stored FX rate per currency; never touches the network (boot must not depend on it)."""
    rates: dict = {settings.base_currency: 1.0}
    for cur in ("USD", "EUR"):
        if cur == settings.base_currency:
            continue
        doc = await db.fx_rates.find_one({"base": cur, "quote": settings.base_currency}, sort=[("date", -1)])
        rates[cur] = doc["rate"] if doc else None
    return rates


async def _migrate_prices(db) -> int:
    for f in PRICE_FIELDS:
        await db.prices.update_many({f: 0}, {"$set": {f: None}})
    winners: dict[tuple, tuple] = {}  # new key -> (_id, as_of)
    losers: list = []
    async for p in db.prices.find({"observed_on": {"$exists": False}}):
        variant = None if p["variant"] == "default" else p["variant"]
        on = _day(p.get("fetched_at"), p.get("as_of"))
        k = (p["card_id"], variant, p["source"], p["kind"], p["grade_key"], on)
        floor = datetime.min.replace(tzinfo=timezone.utc)
        rank = p.get("as_of") or floor
        if k in winners:
            old_id, old_rank = winners[k]
            if rank > old_rank:
                losers.append(old_id)
                winners[k] = (p["_id"], rank)
            else:
                losers.append(p["_id"])
        else:
            winners[k] = (p["_id"], rank)
    if losers:
        await db.prices.delete_many({"_id": {"$in": losers}})
    for k, (_id, _) in winners.items():
        try:
            await db.prices.update_one({"_id": _id}, {"$set": {"variant": k[1], "observed_on": k[5]}})
        except DuplicateKeyError:  # an already-migrated row owns this key (interrupted earlier run)
            await db.prices.delete_one({"_id": _id})
    return len(winners)


def _nest_latest(old: dict) -> dict:
    new: dict = {}
    for src, variants in (old or {}).items():
        for var, v in variants.items():
            v = {k: (None if k in PRICE_FIELDS and not x else x) for k, x in v.items()}
            slot = NO_VARIANT if src == "cardmarket" else var
            new.setdefault(src, {}).setdefault("market", {}).setdefault("raw", {})[slot] = v
    return new


async def _migrate_cards(db) -> int:
    rates = await _cached_rates(db)
    n, ops = 0, []
    async for c in db.cards.find({"price_schema": {"$ne": PRICE_SCHEMA}},
                                 {"variants": 1, "latest_price": 1, "price_base": 1}):
        old = c.get("latest_price") or {}
        upd: dict = {"price_schema": PRICE_SCHEMA}
        if old:
            latest = _nest_latest(old)
            upd["latest_price"] = latest
            base = best_base(latest, rates)
            upd["price_base"] = base if base is not None else (c.get("price_base") or None)
        elif c.get("price_base") == 0:
            upd["price_base"] = None
        if c.get("variants") == ["normal"] and not old.get("tcgplayer"):
            upd["variants"] = []  # was a placeholder, not a real TCGplayer variant
        ops.append(UpdateOne({"_id": c["_id"]}, {"$set": upd}))
        n += 1
        if len(ops) >= BATCH:
            await db.cards.bulk_write(ops, ordered=False)
            ops = []
    if ops:
        await db.cards.bulk_write(ops, ordered=False)
    return n


async def _migrate_items(db) -> int:
    from app.services.collection import make_stack_key  # local: avoid import cycle with db.mongo

    n = 0
    async for it in db.collection_items.find({"variant": "normal"}):
        card = await db.cards.find_one({"_id": it["card_id"]}, {"variants": 1})
        if not card or card.get("variants") != []:
            continue
        g = it.get("grading")
        key = make_stack_key(it["card_id"], None, it["language"], it.get("condition"), g)
        twin = await db.collection_items.find_one({"stack_key": key, "_id": {"$ne": it["_id"]}}, {"_id": 1})
        if twin:
            await db.collection_items.update_one({"_id": twin["_id"]}, {"$inc": {"quantity": it["quantity"]}})
            await db.collection_items.delete_one({"_id": it["_id"]})
        else:
            await db.collection_items.update_one({"_id": it["_id"]}, {"$set": {"variant": None, "stack_key": key}})
        n += 1
    return n


async def migrate(db) -> dict:
    stats = {"prices": await _migrate_prices(db), "cards": await _migrate_cards(db),
             "items": await _migrate_items(db)}
    try:
        await db.prices.drop_index(OLD_INDEX)
    except Exception:  # noqa: BLE001 - index absent on fresh databases
        pass
    if any(stats.values()):
        log.info("price model v2 migration: %s", stats)
    return stats
