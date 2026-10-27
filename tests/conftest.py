import uuid
from datetime import datetime, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.db import mongo
from app.providers.catalog.pokemontcg import map_card

CARD = {"id": "base1-4", "name": "Charizard", "number": "4", "supertype": "Pokémon",
        "types": ["Fire"], "rarity": "Rare Holo", "set": {"id": "base1", "name": "Base", "printedTotal": 102},
        "tcgplayer": {"updatedAt": "2026/10/27", "prices": {"holofoil": {"low": 100.5, "mid": 200, "high": 400, "market": 250.1}}},
        "cardmarket": {"updatedAt": "2026/10/27", "prices": {"trendPrice": 180.0}}}


def make_card(set_id: str, num: str, priced: bool = True) -> dict:
    raw = {**CARD, "id": f"{set_id}-{num}", "number": num, "set": {"id": set_id, "name": set_id, "printedTotal": 10}}
    if not priced:
        raw = {**raw, "tcgplayer": {}, "cardmarket": {}}
    return map_card(raw)


class FakeCatalog:
    """Canned CatalogProvider; sets in `fail` raise like the flaky upstream."""

    def __init__(self, cards_by_set: dict[str, list[dict]], fail: set[str] = frozenset()):
        self.cards_by_set, self.fail, self.calls = cards_by_set, set(fail), []

    async def list_sets(self):
        return [{"_id": f"pokemon:{s}", "tcg": "pokemon", "external_id": s, "name": s,
                 "release_date": None} for s in self.cards_by_set]

    async def iter_cards(self, set_id=None):
        self.calls.append(set_id)
        if set_id in self.fail:
            raise RuntimeError("upstream 500")
        for c in self.cards_by_set[set_id]:
            yield c


@pytest.fixture
async def db():
    """Throwaway database on the compose mongo; global accessors point at it for the test."""
    client = AsyncIOMotorClient(settings.mongo_url, tz_aware=True, serverSelectionTimeoutMS=3000)
    old = mongo._client, mongo._db
    mongo._client, mongo._db = client, client[f"moc_test_{uuid.uuid4().hex[:8]}"]
    await mongo.init_indexes()
    # Today's FX cached up front so services never reach the network.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await mongo._db.fx_rates.insert_one({"date": today, "base": "USD", "quote": "EUR", "rate": 0.9})
    yield mongo._db
    await client.drop_database(mongo._db.name)
    client.close()
    mongo._client, mongo._db = old
