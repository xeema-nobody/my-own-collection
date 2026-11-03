"""Picks the configured catalog provider (`CATALOG_PROVIDER`). TCGdex needs an index of our own sets/cards
because its ids differ from the pokemontcg.io ids every collection row is keyed on."""
from app.config import settings
from app.db.mongo import get_db
from app.providers.catalog.pokemontcg import PokemonTcgCatalog
from app.providers.catalog.tcgdex import CatalogIndex, TcgdexCatalog


async def build_index(db) -> CatalogIndex:
    sets = {s["external_id"]: s async for s in db.sets.find({"tcg": "pokemon"}, {"external_id": 1, "name": 1, "total": 1})}
    numbers: dict[str, set[str]] = {}
    async for c in db.cards.find({"tcg": "pokemon"}, {"number": 1, "set.id": 1}):
        numbers.setdefault(c["set"]["id"], set()).add(c["number"])
    return CatalogIndex(sets=sets, numbers=numbers)


async def get_catalog():
    name = settings.catalog_provider
    if name == "tcgdex":
        return TcgdexCatalog(await build_index(get_db()))
    if name == "pokemontcg":
        return PokemonTcgCatalog()
    raise ValueError(f"unknown CATALOG_PROVIDER {name!r} (pokemontcg | tcgdex)")
