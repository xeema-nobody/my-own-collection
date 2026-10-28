"""Shared types + helpers for scraped price adapters. Pure: no network, no DB."""
import re
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from app.providers.price import PricePoint

SOLD_WINDOW_DAYS = 90   # D-A: sold stats = last N sales within the window
SOLD_SAMPLE = 10

Status = Literal["ok", "needs_match", "not_found", "login_timeout", "blocked", "error"]

GRADER_RE = re.compile(
    r"\b(PSA|BGS|CGC|SGC|TAG|ACE|AGS)\s*(\d{1,2}(?:\.\d)?)(?:\s*(Black|Pristine))?\b", re.I)
JAPANESE_RE = re.compile(r"\b(JP|JPN|Japanese|Japan)\b", re.I)


@dataclass
class Candidate:
    url: str
    title: str
    name: str
    set_name: str
    number: str
    language: str = "en"
    score: float = 0.0


@dataclass
class Sale:
    source: str
    listing_id: str
    grade_key: str          # 'raw' | 'PSA9' | ...
    price: int              # cents
    currency: str
    sold_on: date
    title: str


@dataclass
class AdapterResult:
    status: Status
    points: list[PricePoint] = field(default_factory=list)
    sales: list[Sale] = field(default_factory=list)
    url: str | None = None
    candidates: list[Candidate] = field(default_factory=list)
    detail: str | None = None
    chart: list[tuple[date, int]] = field(default_factory=list)   # history seed (3.6)


def parse_money(text: str) -> int | None:
    """'$1,450.00' / '24,56 €' / '2.400,00 €' / '$53' -> cents. '-' / '' -> None."""
    t = re.sub(r"[^\d.,]", "", text or "")
    if not t:
        return None
    dec = None
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
    else:
        for ch in (",", "."):
            if ch in t and len(t) - t.rfind(ch) == 3:
                dec = ch
    whole, frac = t.rsplit(dec, 1) if dec else (t, "00")
    return int(re.sub(r"[.,]", "", whole) or 0) * 100 + int(frac.ljust(2, "0")[:2])


def grade_from_title(title: str) -> str:
    """Grader + grade in a listing title -> grade_key ('PSA9', 'BGS10Black'); none -> 'raw'."""
    m = GRADER_RE.search(title)
    if not m:
        return "raw"
    key = f"{m.group(1).upper()}{float(m.group(2)):g}"
    return key + (m.group(3) or "").title()


def sold_points(sales: list[Sale], source: str, today: date, url: str | None = None) -> list[PricePoint]:
    """One kind=sold point per graded grade_key: median/low/high over the last SOLD_SAMPLE sales
    within SOLD_WINDOW_DAYS. Raw sales are skipped (condition unknown)."""
    cutoff = today - timedelta(days=SOLD_WINDOW_DAYS)
    by_grade: dict[str, list[Sale]] = {}
    for s in sales:
        if s.grade_key != "raw" and s.sold_on >= cutoff:
            by_grade.setdefault(s.grade_key, []).append(s)
    out: list[PricePoint] = []
    for grade, rows in sorted(by_grade.items()):
        rows = sorted(rows, key=lambda r: r.sold_on, reverse=True)[:SOLD_SAMPLE]
        prices = [r.price for r in rows]
        out.append({"source": source, "kind": "sold", "grade_key": grade, "variant": None,
                    "currency": rows[0].currency, "as_of": max(r.sold_on for r in rows),
                    "median": int(statistics.median(prices)), "low": min(prices),
                    "high": max(prices), "avg": round(statistics.fmean(prices)), "market": None,
                    "sample_size": len(prices), "url": url})
    return out
