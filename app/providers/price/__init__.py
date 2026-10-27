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


def registry() -> list[SourceInfo]:
    """Known price sources and whether they are usable now (config read at call time)."""
    return [
        SourceInfo("pokemontcg", "pokemontcg.io aggregate (TCGplayer USD + Cardmarket EUR)",
                   ("market",), "raw only", True, "embedded in the catalog payload"),
        SourceInfo("pricecharting", "PriceCharting", ("sold", "market"), "raw + graded (verify)",
                   False, "browser fetcher, Phase 3"),
        SourceInfo("cardmarket", "Cardmarket (direct)", ("sold", "market"), "raw (+ graded if listed)",
                   False, "browser fetcher, Phase 3"),
        SourceInfo("altxyz", "alt.xyz", ("sold",), "graded", False, "browser fetcher, Phase 3"),
        SourceInfo("manual", "Manual sales", ("sold",), "any", True, "POST /api/cards/{id}/sales"),
    ]


def registry_json() -> list[dict]:
    return [{"id": s.id, "label": s.label, "kinds": list(s.kinds), "grades": s.grades,
             "enabled": s.enabled, "note": s.note} for s in registry()]

