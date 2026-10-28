from datetime import datetime, timezone

from app.config import settings
from app.services import collection as coll
from app.services.matching import product_info
from app.services.pricing import get_rates, store_card_prices, store_scraped_points
from app.services.valuation import headline_rule, spread
from conftest import make_card

CID = "pokemon:a-1"


def test_spread_flags_far_source_only_with_three_sources():
    s = spread({"a": 2400, "b": 2500, "c": 5000, "d": None})
    assert s["median"] == 2500 and s["outliers"] == ["c"] and s["pct"]["c"] == 100
    assert spread({"a": 2400, "b": 5000})["outliers"] == []   # two sources: gap only
    assert spread({"a": None})["median"] is None


def test_spread_threshold_is_a_setting():
    class Cfg:
        outlier_pct = 150
    assert spread({"a": 100, "b": 100, "c": 200}, Cfg)["outliers"] == []


def test_headline_rule_text():
    sold = {"kind": "sold", "thin": False, "sample_size": 5, "source": "altxyz"}
    assert "sold median of last 5" in headline_rule(sold, None)
    assert "thin sold: 2 sales" in headline_rule({**sold, "thin": True, "sample_size": 2}, None)
    mk = {"kind": "market", "thin": False, "sample_size": None, "source": "pricecharting"}
    assert "#1 in preference order" in headline_rule(mk, None, settings)
    assert headline_rule(mk, "tcgplayer") == "only tcgplayer"


def test_product_info_version_and_slug():
    p = product_info("https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Mew-ex-V5-MEW205?language=1")
    assert p["version"] == "V5" and p["slug"] == "Mew-ex-V5-MEW205"
    assert product_info("https://www.pricecharting.com/game/pokemon-151/mew-ex-205")["version"] is None
    assert product_info(None) is None


async def test_compare_card_carries_age_and_stale(db):
    rates = await get_rates(db)
    doc = make_card("a", "1")
    await db.cards.insert_one(doc)
    await store_card_prices(db, doc, rates, "2026-10-01")
    await store_scraped_points(db, CID, [{"source": "pricecharting", "kind": "market", "grade_key": "raw",
                                          "variant": None, "currency": "USD", "market": 2500, "as_of": None}],
                               "2026-10-27")
    r = await coll.compare_card(db, CID)
    pc = r["sources"]["pricecharting"]
    assert pc["observed_on"] == "2026-10-27" and pc["as_of"] is None and pc["stale"] is False
    assert r["sources"]["tcgplayer"]["observed_on"] == "2026-10-01"
    assert r["headline_rule"] and r["spread"]["median"] is not None and r["grade_key"] == "raw"
    assert await coll.compare_card(db, "pokemon:nope") is None


async def test_stale_catalog_marked(db):
    doc = make_card("a", "1")
    await db.cards.insert_one(doc)
    old = datetime(2024, 1, 1, tzinfo=timezone.utc)
    await db.cards.update_one({"_id": CID}, {"$set": {"latest_price.cardmarket.market.raw._": {
        "market": 1663, "currency": "EUR", "as_of": old, "observed_on": "2026-10-01"}}})
    r = await coll.compare_card(db, CID)
    assert r["sources"]["cardmarket"]["stale"] is True


async def test_spread_ignores_sources_priced_differently(db):
    from app.services.collection import _comparable
    best = {"match": "exact"}
    srcs = {"a": {"value": 100, "match": "exact"}, "b": {"value": 10, "match": "raw_fallback"},
            "c": {"value": None, "match": "none"}}
    assert _comparable(best, srcs) == {"a": 100}
