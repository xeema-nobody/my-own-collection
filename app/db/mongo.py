from datetime import timezone

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, TEXT

from app.config import settings
from app.db import migrate_prices_v2
from app.services import jobs

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        # Bounded timeouts: a Mongo hang must not stall requests for 30s.
        _client = AsyncIOMotorClient(
            settings.mongo_url, tz_aware=True, tzinfo=timezone.utc,
            serverSelectionTimeoutMS=5_000, connectTimeoutMS=5_000, socketTimeoutMS=30_000,
        )
    return _client


def get_db() -> AsyncIOMotorDatabase:
    global _db
    if _db is None:
        _db = get_client()[settings.mongo_db]
    return _db


async def init_indexes() -> None:
    db = get_db()
    await db.cards.create_index(
        [("name", TEXT), ("search_text", TEXT)],
        weights={"name": 10, "search_text": 1}, name="cards_text",
    )
    await db.cards.create_index([("name_norm", ASCENDING)])
    await db.cards.create_index([("tcg", 1), ("set.id", 1), ("number_sort", 1)])
    await db.cards.create_index([("tcg", 1), ("rarity", 1)])
    await db.cards.create_index([("tcg", 1), ("types", 1)])
    await db.sets.create_index([("tcg", 1), ("release_date", -1)])
    # One stack per card/variant/language/condition/grade; slabs with a cert are unique via cert.
    await db.collection_items.create_index(
        [("stack_key", ASCENDING)], unique=True
    )
    await db.collection_items.create_index([("card_id", ASCENDING)])
    # Rows must carry observed_on (and old index gone) before the v2 unique key can build.
    await migrate_prices_v2.migrate(db)
    await db.prices.create_index(
        [("card_id", 1), ("variant", 1), ("source", 1), ("kind", 1), ("grade_key", 1), ("observed_on", 1)],
        unique=True, name="prices_observation_key",
    )
    await db.sales.create_index([("card_id", 1), ("grade_key", 1), ("source", 1), ("sold_at", -1)])
    await db.collection_snapshots.create_index([("date", ASCENDING)], unique=True)
    await db.fx_rates.create_index([("date", 1), ("base", 1), ("quote", 1)], unique=True)
    await db.jobs.create_index([("started_at", DESCENDING)])
    # Orphans must be closed before the unique index can build over existing `running` rows.
    await jobs.mark_orphans(db)
    await db.jobs.create_index([("type", ASCENDING)], unique=True, name="jobs_one_running_per_type",
                               partialFilterExpression={"status": "running"})
