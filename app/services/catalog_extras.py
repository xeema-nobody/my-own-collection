"""Import the cards/sets TCGdex has and pokemontcg.io lacks (decision 2026-11-10: catalog only, never the collection).

Wraps a `TcgdexCatalog` so a normal `import_catalog` run (a) only stores the wanted new sets (not the digital
Pocket sets etc.), (b) fetches only the card numbers we do not hold, no price refresh for known cards.
"""
from app.db.mongo import get_db
from app.providers.catalog.tcgdex import TcgdexCatalog, card_number
from app.services.catalog_import import import_catalog
from app.services.catalog_provider import build_index

# Known sets that miss cards upstream (our id == TCGdex id). cel25c (other numbering) is deliberately left out.
EXTRA_CARDS_SETS = ["svp", "swshp", "sve", "ecard2", "det1"]
# Whole sets we never had (TCGdex ids).
NEW_SETS = ["mep", "mee", "mfb", "2023sv", "2024sv", "jumbo", "fut2020", "rc", "30th-c",
            "tk-dp-l", "tk-dp-m", "tk-hs-r", "tk-hs-g", "tk-bw-z", "tk-bw-e",
            "tk-xy-sy", "tk-xy-n", "tk-xy-b", "tk-xy-w", "tk-xy-latio", "tk-xy-latia", "tk-xy-su", "tk-xy-p",
            "tk-sm-l", "tk-sm-r"]


class ExtrasCatalog:
    """Same provider interface as TcgdexCatalog, restricted to the wanted sets and the missing numbers."""
    tcg = "pokemon"

    def __init__(self, inner: TcgdexCatalog, new_sets: list[str]):
        self.inner, self.new_sets = inner, set(new_sets)

    async def list_sets(self) -> list[dict]:
        return [s for s in await self.inner.list_sets()
                if s["external_id"] in self.inner.index.sets or s["external_id"] in self.new_sets]

    async def iter_cards(self, set_id: str):
        known = self.inner.index.numbers.get(set_id, set())
        sets, mapping = await self.inner._tcgdex_sets()
        tid = mapping.get(set_id, set_id)
        detail = await self.inner._get(f"/sets/{tid}")
        only = {f"pokemon:{set_id}-{card_number(c['localId'])}" for c in detail.get("cards", [])
                if card_number(c["localId"]) not in known}
        if not only:
            return
        async for card in self.inner.iter_cards(set_id, only=only):
            yield card


async def import_extras(sets: list[str] | None = None) -> dict:
    """Idempotent. `sets` limits the run (default: everything above)."""
    index = await build_index(get_db())
    wanted = sets or EXTRA_CARDS_SETS + NEW_SETS
    provider = ExtrasCatalog(TcgdexCatalog(index), [s for s in wanted if s in NEW_SETS])
    return await import_catalog(wanted, provider=provider, trigger="extras")
