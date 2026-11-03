"""Helpers shared by every catalog provider: text normalisation, price units and the price-point extractor."""
import re
import unicodedata
from datetime import datetime, timezone


def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _cents(v) -> int | None:
    # Upstream sends 0 for "no data"; a price of 0 is never real, so it is missing (None).
    return None if not v else round(float(v) * 100)


def _date(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.strptime(s[:10].replace("/", "-"), "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _num_sort(number: str) -> int:
    m = re.search(r"\d+", number or "")
    return int(m.group()) if m else 0


def extract_prices(doc: dict) -> list[dict]:
    """Aggregate price points (kind=market, raw) from the embedded tcgplayer/cardmarket blocks."""
    out: list[dict] = []
    raw = doc["_prices_raw"]
    tp, cm = raw["tcgplayer"], raw["cardmarket"]
    base = {"kind": "market", "grade_key": "raw"}
    as_of = _date(tp.get("updatedAt"))
    for variant, p in (tp.get("prices") or {}).items():
        out.append({**base, "source": "tcgplayer", "variant": variant, "currency": "USD", "as_of": as_of,
                    "url": tp.get("url"), "low": _cents(p.get("low")), "avg": _cents(p.get("mid")),
                    "high": _cents(p.get("high")), "market": _cents(p.get("market"))})
    cp = cm.get("prices") or {}
    if cp:  # one price per card, no per-variant split
        out.append({**base, "source": "cardmarket", "variant": None, "currency": "EUR",
                    "as_of": _date(cm.get("updatedAt")), "url": cm.get("url"),
                    "low": _cents(cp.get("lowPrice")), "avg": _cents(cp.get("averageSellPrice")),
                    "trend": _cents(cp.get("trendPrice")), "market": _cents(cp.get("trendPrice")),
                    "avg7": _cents(cp.get("avg7")), "avg30": _cents(cp.get("avg30"))})
    return out
