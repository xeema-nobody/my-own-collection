"""Grading-company cert lookup: shared types. A provider turns (grader, cert) into a CertInfo and
never raises for not-found / blocked / fetcher down: the link is always built for a valid cert."""
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Protocol

FOUND, NOT_FOUND, BLOCKED, UNAVAILABLE, LINK_ONLY, INVALID = (
    "found", "not_found", "blocked", "unavailable", "link_only", "invalid")

RESTART_HINT = "restart the fetcher: scripts/fetcher.sh restart"


@dataclass
class CertInfo:
    grader: str
    cert: str
    status: str                       # found | not_found | blocked | unavailable | link_only | invalid
    url: str | None = None            # the grader's report page (built from the template, even if unread)
    name: str | None = None
    number: str | None = None         # as printed ('011/078', '205', 'SWSH285')
    printed_total: int | None = None
    set_name: str | None = None
    year: int | None = None
    language: str | None = None
    variant: str | None = None
    grade: float | None = None
    tier: str | None = None           # 'GEM MINT'
    subgrades: dict[str, float] = field(default_factory=dict)
    population: dict[str, int] = field(default_factory=dict)
    detail: str | None = None         # why not found / blocked / link-only (shown to the user)
    fetched_at: datetime | None = None

    def to_doc(self) -> dict:
        return asdict(self)

    @classmethod
    def from_doc(cls, d: dict) -> "CertInfo":
        keys = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in keys})


class CertProvider(Protocol):
    grader: str

    async def lookup(self, cert: str) -> CertInfo: ...


def now() -> datetime:
    return datetime.now(timezone.utc)


def clean_cert(cert: str | None) -> str | None:
    """Digits only, no signs or spaces; None when anything else is in it (never build a URL from it)."""
    c = (cert or "").strip().lstrip("#").strip()
    return c if re.fullmatch(r"\d{1,12}", c) else None


def split_number(raw: str | None) -> tuple[str | None, int | None]:
    """'011/078' -> ('011/078', 78); '205' -> ('205', None); junk -> (None, None)."""
    s = (raw or "").strip()
    if not s:
        return None, None
    m = re.fullmatch(r"([A-Za-z]{0,5}\d{1,4}[A-Za-z]?)\s*/\s*[A-Za-z]{0,5}(\d{1,4})", s)
    if m:
        return s, int(m.group(2))
    return (s, None) if re.fullmatch(r"[A-Za-z]{0,6}\d{0,4}[A-Za-z]{0,3}-?\d{0,3}", s) else (None, None)


def grade_from(raw: str | None) -> float | None:
    m = re.search(r"\d+(?:\.\d)?", raw or "")
    return float(m.group()) if m else None
