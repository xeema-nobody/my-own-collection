import pytest
from pymongo.errors import DuplicateKeyError

from app.db import mongo


async def test_unused_text_index_is_dropped_and_not_recreated(db):
    await db.cards.create_index([("name", "text"), ("search_text", "text")], name="cards_text")
    assert "cards_text" in await db.cards.index_information()
    await mongo.init_indexes()
    assert "cards_text" not in await db.cards.index_information()
    await mongo.init_indexes()  # idempotent when already gone
    assert "name_norm_1" in await db.cards.index_information()


async def test_unique_stack_key(db):
    await db.collection_items.insert_one({"stack_key": "k1", "card_id": "c"})
    with pytest.raises(DuplicateKeyError):
        await db.collection_items.insert_one({"stack_key": "k1", "card_id": "c"})


async def test_unique_snapshot_date_and_fx_rate(db):
    await db.collection_snapshots.insert_one({"date": "2026-10-28"})
    with pytest.raises(DuplicateKeyError):
        await db.collection_snapshots.insert_one({"date": "2026-10-28"})
    fx = {"date": "2026-10-28", "base": "GBP", "quote": "EUR", "rate": 1.1}
    await db.fx_rates.insert_one(dict(fx))
    with pytest.raises(DuplicateKeyError):
        await db.fx_rates.insert_one(dict(fx))
    await db.fx_rates.insert_one({**fx, "quote": "USD"})  # another pair, same day: fine


async def test_alert_event_key_unique_only_when_string(db):
    await db.alert_events.insert_one({"key": "fetch-skipped:2026-10-28"})
    with pytest.raises(DuplicateKeyError):
        await db.alert_events.insert_one({"key": "fetch-skipped:2026-10-28"})
    # rule events carry no key and may repeat
    await db.alert_events.insert_many([{"rule": "a"}, {"rule": "a"}, {"key": None}, {"key": None}])


async def test_one_running_job_per_type(db):
    await db.jobs.insert_one({"type": "price_refresh", "status": "running"})
    with pytest.raises(DuplicateKeyError):
        await db.jobs.insert_one({"type": "price_refresh", "status": "running"})
    await db.jobs.insert_one({"type": "catalog_import", "status": "running"})      # other type ok
    await db.jobs.insert_many([
        {"type": "price_refresh", "status": "ok"}, {"type": "price_refresh", "status": "error"}])  # finished ones repeat
    await db.jobs.update_one({"type": "price_refresh", "status": "running"}, {"$set": {"status": "ok"}})
    await db.jobs.insert_one({"type": "price_refresh", "status": "running"})        # slot freed


async def test_price_observation_key_unique(db):
    p = {"card_id": "c", "variant": "normal", "source": "cardmarket", "kind": "market",
         "grade_key": "raw", "observed_on": "2026-10-28", "market": 1}
    await db.prices.insert_one(dict(p))
    with pytest.raises(DuplicateKeyError):
        await db.prices.insert_one(dict(p))
    await db.prices.insert_one({**p, "observed_on": "2026-10-29"})
