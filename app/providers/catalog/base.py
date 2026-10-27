from typing import AsyncIterator, Protocol


class CatalogProvider(Protocol):
    tcg: str

    def iter_cards(self, set_id: str | None = None) -> AsyncIterator[dict]:
        """Yield normalised card docs (see services.catalog_import schema)."""
        ...

    async def list_sets(self) -> list[dict]: ...
