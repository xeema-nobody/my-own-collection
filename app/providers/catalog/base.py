from typing import AsyncIterator, Protocol


class CatalogProvider(Protocol):
    tcg: str

    def iter_cards(self, set_id: str | None = None, only: set[str] | None = None) -> AsyncIterator[dict]:
        """Yield normalised card docs (see services.catalog_import schema).

        `only` (card `_id`s) is a hint for per-card APIs: skip the rest. Providers that page whole sets may ignore it.
        A doc with `_prices_only` is not written to `cards`, only its prices are stored; `_sources` lists the
        catalog price sources the provider covers (default: all)."""
        ...

    async def list_sets(self) -> list[dict]: ...
