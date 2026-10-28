"""alt.xyz adapter: sold listings with per-company grades, anonymous. No product matching step:
the search page is filtered to tiles with the card's number, set and rarity.
Last verified against tests/fixtures: 2026-10-27."""
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.config import settings
from app.providers.fetcher import FetcherClient
from app.providers.price.base import (
    GRADER_RE, AdapterResult, Sale, grade_from_title, parse_money, sold_points)
from app.providers.price.match import _tokens, norm, norm_number, strip_variant
from app.providers.price.resolve import safe_fetch

SOURCE = "altxyz"
BASE = "https://alt.xyz"
SPA_WAIT_MS = 5000
NEXT_PAGE = "Go to next page"   # the list pages client-side (no URL param), so page N = N-1 clicks


def search_url(card: dict) -> str:
    # set + rarity in the query keeps other prints (e.g. Ultra Premium Collection) off the first page
    parts = [card["name"], card["number"], (card.get("set") or {}).get("name"), card.get("rarity")]
    return f"{BASE}/browse?query={quote(' '.join(p for p in parts if p))}"


def _tile(link):
    """Smallest ancestor of a tile's text link that holds exactly this listing."""
    node = link
    while node.parent is not None and len({a["href"] for a in node.parent.select('a[href$="/sold"]')}) == 1:
        node = node.parent
    return node


def parse_tiles(html: str) -> list[dict]:
    """Raw sold tiles: {id, title, name, number, grade_key, price, sold_on, strings}."""
    out, seen = [], set()
    for a in BeautifulSoup(html, "html.parser").select('a[href^="/itm/"][href$="/sold"]'):
        lid = a["href"].split("/")[2]
        if lid in seen or not a.get_text(strip=True):
            continue
        seen.add(lid)
        s = list(_tile(a).stripped_strings)
        try:
            sold_on = datetime.strptime(s[-1], "%b %d, %Y").date()
        except ValueError:
            continue
        ident = next((x for x in s if "#" in x), "")
        price = next((parse_money(x) for x in s if x.startswith("$")), None)
        grade = next((x for x in s if GRADER_RE.fullmatch(x)), None)
        if price is None:
            continue
        out.append({"id": lid, "title": s[0], "name": ident.rpartition("#")[0].strip(),
                    "number": ident.rpartition("#")[2].strip(), "grade_key":
                    grade_from_title(grade) if grade else "raw", "price": price, "sold_on": sold_on})
    return out


def tile_matches(card: dict, t: dict, check_rarity: bool = True) -> bool:
    """Same card and print: number + base name, set tokens and rarity inside the tile title."""
    if norm_number(t["number"]) != norm_number(card["number"]):
        return False
    if strip_variant(t["name"])[0] != strip_variant(card["name"])[0]:
        return False
    if not _tokens((card.get("set") or {}).get("name") or "") <= _tokens(t["title"]):
        return False
    rarity = norm(card.get("rarity"))
    return not (check_rarity and rarity) or rarity in norm(t["title"])


def parse_sold(html: str, card: dict) -> list[Sale]:
    tiles = parse_tiles(html)
    # alt titles name the rarity only for some prints ("Hyper Rare"); filter on it only when they do
    rarity = norm(card.get("rarity"))
    check = any(tile_matches(card, t, False) and rarity in norm(t["title"]) for t in tiles)
    return [Sale(SOURCE, t["id"], t["grade_key"], t["price"], "USD", t["sold_on"], t["title"])
            for t in tiles if tile_matches(card, t, check)]


def _stop_paging(tiles: list[dict], seen: set[str], cutoff: date) -> bool:
    """Last page read when it brought nothing new or its oldest listing is outside the window
    (the list is newest first)."""
    new = [t for t in tiles if t["id"] not in seen]
    return not new or min(t["sold_on"] for t in tiles) < cutoff


class AltXyzProvider:
    source, site = SOURCE, "altxyz"

    async def fetch(self, card: dict, client: FetcherClient, known_url: str | None = None,
                    today: date | None = None) -> AdapterResult:
        url = known_url or search_url(card)
        today = today or datetime.now(timezone.utc).date()
        cutoff = today - timedelta(days=settings.altxyz_max_age_days)
        sales: list[Sale] = []
        seen: set[str] = set()
        for page in range(1, max(settings.altxyz_max_pages, 1) + 1):
            r = await safe_fetch(client, self.site, url, wait_selector='a[href^="/itm/"]',   # SPA hydrated
                                 click_text="Sold listings", click_labels=[NEXT_PAGE] * (page - 1),
                                 wait_ms=SPA_WAIT_MS)
            if isinstance(r, AdapterResult):
                if page == 1:
                    return r
                break     # later page failed: keep what the earlier pages gave
            tiles = parse_tiles(r.html)
            fresh = [s for s in parse_sold(r.html, card) if s.listing_id not in seen]
            sales += [s for s in fresh if s.sold_on >= cutoff]
            stop = _stop_paging(tiles, seen, cutoff)
            seen |= {t["id"] for t in tiles}
            if stop:
                break
        points = sold_points(sales, SOURCE, today, url)
        if not points:
            return AdapterResult("not_found", sales=sales, url=url,
                                 detail="no graded sold listings for this print")
        return AdapterResult("ok", points=points, sales=sales, url=url)
