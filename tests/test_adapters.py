from datetime import date
from pathlib import Path

import httpx
import pytest

from app.providers.fetcher import FetcherClient, FetcherUnavailable
from app.providers.price import get_provider, registry
from app.providers.price import altxyz, cardmarket, pricecharting
from app.providers.price.base import grade_from_title, parse_money, sold_points, Sale
from app.providers.price.match import pick

FX = Path(__file__).parent / "fixtures"
CARD = {"_id": "pokemon:sv3pt5-205", "name": "Mew ex", "number": "205", "language": "en",
        "rarity": "Hyper Rare", "set": {"id": "sv3pt5", "name": "151"}}
TODAY = date(2026, 10, 27)


def fx(rel):
    return (FX / rel).read_text()


def by(points, **kw):
    return [p for p in points if all(p.get(k) == v for k, v in kw.items())]


def test_parse_money():
    assert parse_money("$1,450.00") == 145000
    assert parse_money("24,56 €") == 2456
    assert parse_money("2.400,00 €") == 240000
    assert parse_money("$53") == 5300
    assert parse_money("-") is None and parse_money("") is None


def test_grade_from_title():
    assert grade_from_title("... MEW EX PSA 9 #205") == "PSA9"
    assert grade_from_title("CGC 8.5") == "CGC8.5"
    assert grade_from_title("BGS 10 Black Label") == "BGS10Black"
    assert grade_from_title("Mew ex Near Mint English") == "raw"


# --- PriceCharting
def test_pc_search_picks_plain_card():
    cands = pricecharting.parse_search(fx("pricecharting/search_mew_ex_205.html"))
    assert len(cands) == 5
    best, _ = pick(CARD, cands)
    assert best and best.url.endswith("/pokemon-scarlet-&-violet-151/mew-ex-205")


def test_pc_product():
    res = pricecharting.parse_product(fx("pricecharting/product_mew_ex_205.html"), "u", TODAY)
    assert res.status == "ok"
    mk = {p["grade_key"]: p["market"] for p in by(res.points, kind="market")}
    assert mk["raw"] == 2567 and mk["G9"] == 4331 and mk["G9.5"] == 9475 and mk["PSA10"] == 22275
    assert mk["BGS10Black"] == 145000 and mk["CGC10Pristine"] == 27389 and "G1" not in mk
    assert all(p["currency"] == "USD" for p in res.points)
    assert len(res.sales) > 100 and len({s.listing_id for s in res.sales}) == len(res.sales)
    assert not any("JP" in s.title.split() for s in res.sales)
    sold = {p["grade_key"]: p for p in by(res.points, kind="sold")}
    assert sold["PSA9"]["sample_size"] <= 10 and sold["PSA9"]["median"] > 0
    assert res.chart and res.chart[0][0] < res.chart[-1][0]


# --- Cardmarket
def test_cm_search_three_versions_is_ambiguous():
    cands = cardmarket.parse_search(fx("cardmarket/search_mew_ex_205.html"))
    ja = [c for c in cands if c.language == "ja"]
    assert len(ja) == 1 and "sv2a" in ja[0].url
    best, ranked = pick(CARD, cands)
    assert best is None and len(ranked) == 3          # V3 / V4 / V5 -> user confirms
    assert all("MEW205" in c.url for c in ranked)


def test_cm_product():
    res = cardmarket.parse_product(fx("cardmarket/product_mew_ex_205.html"), "u")
    mk, ask = by(res.points, kind="market")[0], by(res.points, kind="ask")[0]
    assert (mk["market"], mk["avg"], ask["low"]) == (2456, 2372, 1498)
    assert mk["source"] == "cardmarket_web" and mk["currency"] == "EUR" and mk["grade_key"] == "raw"


# --- alt.xyz
def test_alt_search_url_has_set_and_rarity():
    assert altxyz.search_url(CARD).endswith("query=Mew%20ex%20205%20151%20Hyper%20Rare")


def test_alt_sold_filtered_to_print():
    html = fx("altxyz/sold_mew_ex_205.html")
    tiles = altxyz.parse_tiles(html)
    assert len(tiles) == 15 and len({t["id"] for t in tiles}) == 15
    sales = altxyz.parse_sold(html, CARD)
    assert 0 < len(sales) < len(tiles)                # Ultra Premium Collection tiles dropped
    assert all("Hyper Rare" in s.title and "Ultra Premium" not in s.title for s in sales)
    pts = sold_points(sales, "altxyz", TODAY)
    assert {p["grade_key"] for p in pts} >= {"PSA10"}
    assert all(p["kind"] == "sold" and p["currency"] == "USD" for p in pts)


def test_sold_points_window_and_sample():
    mk = lambda i, d, p: Sale("s", str(i), "PSA9", p, "USD", d, "t")
    sales = [mk(i, date(2026, 10, 1 + i % 20), 1000 + i) for i in range(15)] + [mk(99, date(2025, 1, 1), 1)]
    (p,) = sold_points(sales, "s", TODAY)
    assert p["sample_size"] == 10 and p["low"] > 1             # old sale excluded
    assert sold_points([Sale("s", "1", "raw", 5, "USD", TODAY, "t")], "s", TODAY) == []


# --- provider flows with a fake fetcher
class FakeFetcher(FetcherClient):
    def __init__(self, pages=None, **resp):
        self.pages, self.resp, self.calls = pages or {}, resp, []

    async def fetch(self, site, url, **kw):
        from app.providers.fetcher import FetchResponse
        self.calls.append((site, url, kw))
        if self.resp:
            return FetchResponse(**self.resp)
        key = next((k for k in self.pages if k in url), None)
        return FetchResponse("ok", url, "t", self.pages[key]) if key else FetchResponse("error", detail="404")


PC_PAGES = {"search-products": fx("pricecharting/search_mew_ex_205.html"),
            "mew-ex-205": fx("pricecharting/product_mew_ex_205.html")}


async def test_pc_flow_search_then_product():
    f = FakeFetcher(PC_PAGES)
    res = await get_provider("pricecharting").fetch(CARD, f, today=TODAY)
    assert res.status == "ok" and len(f.calls) == 2 and res.url.endswith("mew-ex-205")


async def test_pc_known_url_skips_search():
    f = FakeFetcher(PC_PAGES)
    await get_provider("pricecharting").fetch(CARD, f, known_url="https://x/mew-ex-205", today=TODAY)
    assert len(f.calls) == 1


async def test_cm_ambiguous_returns_candidates():
    f = FakeFetcher({"Products/Search": fx("cardmarket/search_mew_ex_205.html")})
    res = await get_provider("cardmarket_web").fetch(CARD, f)
    assert res.status == "needs_match" and len(res.candidates) == 3 and not res.points


async def test_alt_flow_requests_sold_toggle():
    f = FakeFetcher({"browse": fx("altxyz/sold_mew_ex_205.html")})
    res = await get_provider("altxyz").fetch(CARD, f, today=TODAY)
    assert res.status == "ok" and f.calls[0][2]["click_text"] == "Sold listings"


@pytest.mark.parametrize("status,expect", [("login_timeout", "login_timeout"), ("blocked", "blocked"),
                                           ("error", "error")])
async def test_fetch_failures_are_results_not_exceptions(status, expect):
    for src in ("pricecharting", "cardmarket_web", "altxyz"):
        res = await get_provider(src).fetch(CARD, FakeFetcher(status=status, detail="x"))
        assert res.status == expect and not res.points


async def test_fetcher_down_is_error_result():
    class Down(FetcherClient):
        async def fetch(self, *a, **k):
            raise FetcherUnavailable("down")
    res = await get_provider("altxyz").fetch(CARD, Down())
    assert res.status == "error" and "down" in res.detail


# --- client
async def test_client_maps_http():
    def handler(req):
        assert req.url.path == "/fetch/altxyz"
        return httpx.Response(200, json={"status": "ok", "html": "<p/>", "title": "t", "final_url": "u"})
    c = FetcherClient("http://f", httpx.MockTransport(handler))
    assert (await c.fetch("altxyz", "https://alt.xyz")).html == "<p/>"
    bad = FetcherClient("http://f", httpx.MockTransport(lambda r: httpx.Response(422, text="no")))
    with pytest.raises(FetcherUnavailable):
        await bad.fetch("altxyz", "https://x")

    def boom(req):
        raise httpx.ConnectError("refused")
    with pytest.raises(FetcherUnavailable):
        await FetcherClient("http://f", httpx.MockTransport(boom)).fetch("altxyz", "https://x")


async def test_client_sends_unattended_flag():
    bodies = []

    def handler(req):
        bodies.append(__import__("json").loads(req.content))
        return httpx.Response(200, json={"status": "ok"})
    await FetcherClient("http://f", httpx.MockTransport(handler), unattended=True).fetch("altxyz", "https://alt.xyz")
    await FetcherClient("http://f", httpx.MockTransport(handler)).fetch("altxyz", "https://alt.xyz")
    assert [b["unattended"] for b in bodies] == [True, False]


def test_registry_ids_are_stored_ids():
    ids = {s.id for s in registry()}
    assert ids == {"tcgplayer", "cardmarket", "pricecharting", "cardmarket_web", "altxyz", "manual"}


def test_alt_rarity_not_in_titles_is_not_filtered():
    tile = lambda i, title: {"id": str(i), "title": title, "name": "Galarian Slowking V", "number": "179",
                             "grade_key": "PSA10", "price": 30000, "sold_on": TODAY}
    card = {"name": "Galarian Slowking V", "number": "179", "set": {"name": "Chilling Reign"},
            "rarity": "Rare Ultra"}
    t = tile(1, "2021 Pokemon Sword and Shield Chilling Reign")
    assert altxyz.tile_matches(card, t, check_rarity=False)
    assert not altxyz.tile_matches(card, t, check_rarity=True)
