"""Price source registry. Providers return `PricePoint`s; services store them as observations."""
from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict

Kind = Literal["sold", "market", "ask"]


class PricePoint(TypedDict, total=False):
    source: str
    kind: Kind
    grade_key: str          # 'raw' | 'PSA9' | ...
    variant: str | None     # None = source has no per-variant price
    currency: str
    as_of: object           # upstream timestamp (datetime | None)
    low: int | None         # cents
    avg: int | None
    median: int | None
    high: int | None
    market: int | None
    sample_size: int | None
    url: str | None


class PriceProvider(Protocol):
    async def fetch(self, card: dict) -> list[PricePoint]: ...


@dataclass(frozen=True)
class SourceInfo:
    id: str
    label: str
    kinds: tuple[str, ...]
    grades: str             # human description of supported grades
    enabled: bool
    note: str = ""


SCRAPED = ("pricecharting", "cardmarket_web", "altxyz")  # fetched on demand via the host fetcher


def registry() -> list[SourceInfo]:
    """Known price sources (ids = ids stored in `prices.source`) and whether they are usable now."""
    return [
        SourceInfo("tcgplayer", "TCGplayer (via pokemontcg.io)", ("market",), "raw only", True,
                   "embedded in the catalog payload, USD per variant"),
        SourceInfo("cardmarket", "Cardmarket trend (via pokemontcg.io)", ("market",), "raw only", True,
                   "embedded in the catalog payload; as_of can be stale"),
        SourceInfo("pricecharting", "PriceCharting", ("sold", "market"),
                   "raw + grade buckets G1..G9.5; 10s per company", True, "browser fetcher"),
        SourceInfo("cardmarket_web", "Cardmarket (direct)", ("market", "ask"), "raw only", True,
                   "browser fetcher (real Chrome)"),
        SourceInfo("altxyz", "alt.xyz", ("sold",), "graded, per company", True, "browser fetcher"),
        SourceInfo("manual", "Manual sales", ("sold",), "any", True, "POST /api/cards/{id}/sales"),
    ]


def get_provider(source: str):
    """Scraped adapter for a source id (lazy import: adapters import this module)."""
    from app.providers.price.altxyz import AltXyzProvider
    from app.providers.price.cardmarket import CardmarketProvider
    from app.providers.price.pricecharting import PriceChartingProvider
    return {"pricecharting": PriceChartingProvider, "cardmarket_web": CardmarketProvider,
            "altxyz": AltXyzProvider}[source]()


def registry_json() -> list[dict]:
    return [{"id": s.id, "label": s.label, "kinds": list(s.kinds), "grades": s.grades,
             "enabled": s.enabled, "note": s.note} for s in registry()]

