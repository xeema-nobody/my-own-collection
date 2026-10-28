"""Cardmarket adapter (direct, source id `cardmarket_web`; `cardmarket` is the pokemontcg.io aggregate).
No sold list and no grades: kinds market (trend / 30d avg) and ask (lowest offer 'From').
Last verified against tests/fixtures: 2026-10-27."""
import re
from datetime import date
from urllib.parse import quote_plus, unquote, urljoin

from bs4 import BeautifulSoup

from app.providers.fetcher import FetcherClient
from app.providers.price import PricePoint
from app.providers.price.base import AdapterResult, Candidate, parse_money
from app.providers.price.resolve import find_product, safe_fetch

SOURCE = "cardmarket_web"
BASE = "https://www.cardmarket.com"
HIT_RE = re.compile(r"^(?P<name>.*?)\s*\((?P<code>[A-Za-z0-9]+)\s+(?P<num>[0-9A-Za-z]+)\)")
LABELS = {"From": "from", "Price Trend": "trend", "30-days average price": "avg30",
          "7-days average price": "avg7", "1-day average price": "avg1"}


def search_url(card: dict) -> str:
    return f"{BASE}/en/Pokemon/Products/Search?searchString={quote_plus(card['name'] + ' ' + card['number'])}"


def parse_search(html: str) -> list[Candidate]:
    out, seen = [], set()
    for a in BeautifulSoup(html, "html.parser").select('a[href*="/Products/Singles/"]'):
        href = a["href"].split("?")[0]
        m = HIT_RE.match(a.get_text(" ", strip=True))
        parts = href.split("/Singles/")[-1].split("/")
        if href in seen or not m or len(parts) < 2:
            continue
        seen.add(href)
        set_seg, code = unquote(parts[0]), m.group("code")
        # Japanese prints live under 'Pokemon-Card-<set>' and use lower-case set codes (sv2a)
        ja = set_seg.startswith("Pokemon-Card") or (code.islower() and not code.isdigit())
        out.append(Candidate(url=urljoin(BASE, href), title=a.get_text(" ", strip=True),
                             name=m.group("name").strip(), set_name=set_seg.replace("-", " "),
                             number=m.group("num"), language="ja" if ja else "en"))
    return out


def parse_product(html: str, url: str) -> AdapterResult:
    vals: dict[str, int | None] = {}
    for dt in BeautifulSoup(html, "html.parser").select("dt"):
        key, dd = LABELS.get(dt.get_text(strip=True)), dt.find_next_sibling("dd")
        if key and dd is not None:
            vals[key] = parse_money(dd.get_text(" ", strip=True))
    base = {"source": SOURCE, "grade_key": "raw", "variant": None, "currency": "EUR", "as_of": None,
            "url": url, "sample_size": None}
    points: list[PricePoint] = []
    if vals.get("trend") is not None or vals.get("avg30") is not None:
        points.append({**base, "kind": "market", "market": vals.get("trend"), "avg": vals.get("avg30"),
                       "low": None, "high": None})
    if vals.get("from") is not None:
        points.append({**base, "kind": "ask", "low": vals["from"], "market": None, "avg": None,
                       "high": None})
    return AdapterResult("ok" if points else "not_found", points=points, url=url,
                         detail=None if points else "no price block on page")


class CardmarketProvider:
    source, site = SOURCE, "cardmarket"

    async def fetch(self, card: dict, client: FetcherClient, known_url: str | None = None,
                    today: date | None = None) -> AdapterResult:
        url, fail = await find_product(card, client, self.site, search_url(card), parse_search, known_url)
        if fail:
            return fail
        r = await safe_fetch(client, self.site, url)
        if isinstance(r, AdapterResult):
            return r
        return parse_product(r.html, url)
