"""PriceCharting adapter. Grades are company-agnostic buckets (G1..G9, G9.5) except 10s, which are
per company (PSA10, CGC10, BGS10Black ...). Last verified against tests/fixtures: 2026-10-27."""
import json
import re
from datetime import date, datetime, timezone
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from app.providers.fetcher import FetcherClient
from app.providers.price import PricePoint
from app.providers.price.base import (
    GRADER_RE, JAPANESE_RE, AdapterResult, Candidate, Sale, grade_from_title, parse_money, sold_points)
from app.providers.price.match import language_of
from app.providers.price.resolve import find_product, safe_fetch

SOURCE = "pricecharting"
BASE = "https://www.pricecharting.com"
CHART_RE = re.compile(r"VGPC\.chart_data\s*=\s*(\{.*?\});", re.S)


def search_url(card: dict) -> str:
    q = f"{card['name']} {card['number']} {(card.get('set') or {}).get('name') or ''}".strip()
    return f"{BASE}/search-products?type=prices&q={quote_plus(q)}"


def parse_search(html: str) -> list[Candidate]:
    out = []
    for row in BeautifulSoup(html, "html.parser").select("table#games_table tr[data-product]"):
        a = row.select_one("td.title a[href]")
        if a is None:
            continue
        title = a.get_text(" ", strip=True)
        name, _, number = title.rpartition("#")
        console = row.select_one(".console-in-title a")
        set_name = console.get_text(" ", strip=True) if console else ""
        out.append(Candidate(url=urljoin(BASE, a["href"]), title=title, name=(name or title).strip(),
                             set_name=set_name, number=number.strip(),
                             language=language_of(set_name)))
    return out


def grade_key_for_label(label: str) -> str | None:
    label = label.strip()
    if label == "Ungraded":
        return "raw"
    m = re.fullmatch(r"Grade (\d(?:\.5)?)", label)
    if m:
        return f"G{m.group(1)}"
    return grade_from_title(label) if GRADER_RE.fullmatch(label) else None


def parse_prices(html: str, url: str) -> list[PricePoint]:
    out: list[PricePoint] = []
    fp = BeautifulSoup(html, "html.parser").select_one("#full-prices")
    for tr in (fp.select("tr") if fp else []):
        tds = tr.find_all("td")
        if len(tds) != 2:
            continue
        key, cents = grade_key_for_label(tds[0].get_text(strip=True)), parse_money(tds[1].get_text())
        if key and cents is not None:
            out.append({"source": SOURCE, "kind": "market", "grade_key": key, "variant": None,
                        "currency": "USD", "as_of": None, "market": cents, "low": None, "avg": None,
                        "high": None, "sample_size": None, "url": url})
    return out


def parse_sales(html: str) -> list[Sale]:
    """Sold rows (eBay/TCGplayer). Japanese listings are dropped: PriceCharting mixes them in."""
    sales, seen = [], set()
    for tr in BeautifulSoup(html, "html.parser").select("tr[id^=ebay-], tr[id^=tcgplayer-]"):
        lid = tr["id"]
        date_td, title_td = tr.select_one("td.date"), tr.select_one("td.title")
        price = tr.select_one("td.numeric .js-price")
        if lid in seen or not (date_td and title_td and price):
            continue
        title = title_td.get_text(" ", strip=True)
        cents = parse_money(price.get_text())
        if cents is None or JAPANESE_RE.search(title):
            continue
        seen.add(lid)
        sales.append(Sale(SOURCE, lid, grade_from_title(title), cents, "USD",
                          date.fromisoformat(date_td.get_text(strip=True)), title))
    return sales


def parse_chart(html: str) -> list[tuple[date, int]]:
    """Monthly ungraded history (free chart seed)."""
    m = CHART_RE.search(html)
    if not m:
        return []
    try:
        series = json.loads(m.group(1)).get("used") or []
    except ValueError:
        return []
    return [(datetime.fromtimestamp(ms / 1000, timezone.utc).date(), int(c)) for ms, c in series if c]


def parse_product(html: str, url: str, today: date) -> AdapterResult:
    sales = parse_sales(html)
    points = parse_prices(html, url) + sold_points(sales, SOURCE, today, url)
    return AdapterResult("ok" if points else "not_found", points=points, sales=sales, url=url,
                         chart=parse_chart(html), detail=None if points else "no prices on page")


class PriceChartingProvider:
    source, site = SOURCE, "pricecharting"

    async def fetch(self, card: dict, client: FetcherClient, known_url: str | None = None,
                    today: date | None = None) -> AdapterResult:
        url, fail = await find_product(card, client, self.site, search_url(card), parse_search, known_url,
                                       product_marker="/game/")
        if fail:
            return fail
        r = await safe_fetch(client, self.site, url)
        if isinstance(r, AdapterResult):
            return r
        return parse_product(r.html, url, today or datetime.now(timezone.utc).date())
