from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.db import migrate_prices_v2
from app.db.models import CollectionIn
from app.providers.catalog.pokemontcg import extract_prices, map_card
from app.services import collection as coll
from app.services.pricing import get_rates, price_for, store_card_prices
from conftest import CARD, make_card

UTC = timezone.utc


async def test_same_day_restore_is_idempotent_next_day_adds_point(db):
    card = make_card("a", "1")
    rates = await get_rates(db)
    await store_card_prices(db, card, rates, observed_on="2026-10-27")
    await store_card_prices(db, card, rates, observed_on="2026-10-27")
    assert await db.prices.count_documents({}) == 2  # tcgplayer holofoil + cardmarket
    await store_card_prices(db, card, rates, observed_on="2026-10-28")
    assert await db.prices.count_documents({}) == 4
    cm = await db.prices.find_one({"source": "cardmarket", "observed_on": "2026-10-28"})
    assert cm["variant"] is None and cm["kind"] == "market" and cm["grade_key"] == "raw"
    assert cm["as_of"] is not None  # upstream date kept as a field, not part of the key


async def test_latest_price_shape_and_base(db):
    rates = await get_rates(db)
    await db.cards.insert_one(make_card("a", "1") | {"_prices_raw": 0})
    await store_card_prices(db, make_card("a", "1"), rates)
    c = await db.cards.find_one({"external_id": "a-1"})
    assert c["latest_price"]["cardmarket"]["market"]["raw"]["_"]["market"] == 18000
    assert c["latest_price"]["tcgplayer"]["market"]["raw"]["holofoil"]["market"] == 25010
    assert c["price_base"] == 18000 and c["price_schema"] == 2
    assert price_for(c, "cardmarket", "holofoil", rates) == (18000, False)
    assert price_for(c, "tcgplayer", "reverse", rates)[1] is True  # variant fallback flagged
    assert price_for(c, "tcgplayer", None, rates, grade_key="PSA9") == (None, False)


def test_zero_upstream_price_is_none():
    c = map_card({**CARD, "tcgplayer": {"updatedAt": "2026/10/27", "prices": {"normal": {"low": 0, "market": 0}}},
                  "cardmarket": {"updatedAt": "2026/10/27", "prices": {"trendPrice": 0, "lowPrice": 0}}})
    assert all(p["market"] is None and p["low"] is None for p in extract_prices(c))


def test_card_without_tcgplayer_variants_has_none():
    assert map_card({**CARD, "tcgplayer": {}})["variants"] == []


def test_variant_none_stack_key_and_validation():
    a = CollectionIn(card_id="x", condition="NM")
    assert a.variant is None
    assert coll.stack_key(a) == coll.stack_key(CollectionIn(card_id="x", condition="NM", variant=None))
    assert coll.stack_key(a) != coll.stack_key(CollectionIn(card_id="x", condition="NM", variant="holofoil"))
    with pytest.raises(ValidationError):
        CollectionIn(card_id="x")


async def test_migration_v2_idempotent(db):
    await db.prices.drop_index("prices_observation_key")
    d = lambda y, m, dd: datetime(y, m, dd, tzinfo=UTC)  # noqa: E731
    base = {"card_id": "pokemon:a-1", "kind": "market", "grade_key": "raw", "currency": "EUR"}
    await db.prices.insert_many([  # two cardmarket rows fetched the same day: newest as_of wins
        {**base, "variant": "default", "source": "cardmarket", "as_of": d(2025, 11, 18), "market": 100, "low": 0,
         "fetched_at": d(2026, 10, 27)},
        {**base, "variant": "default", "source": "cardmarket", "as_of": d(2026, 10, 20), "market": 200, "low": 0,
         "fetched_at": d(2026, 10, 27)},
        {**base, "variant": "holofoil", "source": "tcgplayer", "as_of": d(2026, 10, 15), "market": 0,
         "fetched_at": d(2026, 10, 27)}])
    old_lp = {"cardmarket": {"default": {"market": 200, "currency": "EUR", "low": 0}},
              "tcgplayer": {"holofoil": {"market": 0, "currency": "USD"}}}
    await db.cards.insert_many([
        {"_id": "pokemon:a-1", "variants": ["holofoil"], "latest_price": old_lp, "price_base": 0},
        {"_id": "pokemon:a-2", "variants": ["normal"], "latest_price": {}, "price_base": None},
        {"_id": "pokemon:a-3", "variants": ["normal"],
         "latest_price": {"tcgplayer": {"normal": {"market": 5, "currency": "USD"}}}}])
    await db.fx_rates.insert_one({"date": "2026-10-26", "base": "EUR", "quote": "EUR", "rate": 1.0})
    await db.collection_items.insert_many([
        {"card_id": "pokemon:a-2", "variant": "normal", "language": "en", "condition": "NM", "grading": None,
         "quantity": 2, "stack_key": "pokemon:a-2|normal|en|NM|||"},
        {"card_id": "pokemon:a-2", "variant": None, "language": "en", "condition": "NM", "grading": None,
         "quantity": 1, "stack_key": "pokemon:a-2||en|NM|||"},
        {"card_id": "pokemon:a-3", "variant": "normal", "language": "en", "condition": "NM", "grading": None,
         "quantity": 1, "stack_key": "pokemon:a-3|normal|en|NM|||"}])

    stats = await migrate_prices_v2.migrate(db)
    assert stats == {"prices": 2, "cards": 3, "items": 1}
    rows = {r["source"]: r async for r in db.prices.find()}
    assert rows["cardmarket"]["market"] == 200 and rows["cardmarket"]["variant"] is None
    assert rows["cardmarket"]["observed_on"] == "2026-10-27" and rows["cardmarket"]["low"] is None
    assert rows["tcgplayer"]["market"] is None
    c1 = await db.cards.find_one({"_id": "pokemon:a-1"})
    assert c1["latest_price"]["cardmarket"]["market"]["raw"]["_"]["market"] == 200
    assert c1["price_base"] == 200 and c1["price_schema"] == 2
    assert (await db.cards.find_one({"_id": "pokemon:a-2"}))["variants"] == []
    assert (await db.cards.find_one({"_id": "pokemon:a-3"}))["variants"] == ["normal"]  # real tcgplayer variant
    mine = [i async for i in db.collection_items.find({"card_id": "pokemon:a-2"})]
    assert len(mine) == 1 and mine[0]["quantity"] == 3 and mine[0]["variant"] is None  # merged stacks
    assert (await db.collection_items.find_one({"card_id": "pokemon:a-3"}))["variant"] == "normal"

    assert await migrate_prices_v2.migrate(db) == {"prices": 0, "cards": 0, "items": 0}


async def _seed_matrix(db):
    await db.cards.insert_one({"_id": "pokemon:m-1", "variants": ["holofoil", "reverse"]})
    base = {"card_id": "pokemon:m-1", "grade_key": "raw", "currency": "EUR", "as_of": None}
    await db.prices.insert_many([
        {**base, "source": "cardmarket", "kind": "market", "variant": None, "observed_on": "2026-10-26", "market": 100},
        {**base, "source": "cardmarket", "kind": "market", "variant": None, "observed_on": "2026-10-27", "market": 120},
        {**base, "source": "cardmarket", "kind": "sold", "variant": None, "observed_on": "2026-10-27",
         "market": None, "median": 90, "sample_size": 5},
        {**base, "source": "tcgplayer", "kind": "market", "variant": "reverse", "currency": "USD",
         "observed_on": "2026-10-27", "market": 1000},
        {**base, "source": "tcgplayer", "kind": "market", "variant": "holofoil", "currency": "USD",
         "observed_on": "2026-10-27", "market": 2000},
        {**base, "source": "pricecharting", "kind": "market", "variant": None, "grade_key": "PSA10",
         "observed_on": "2026-10-27", "market": 5000},
        {**base, "source": "tcgplayer", "kind": "market", "variant": None, "observed_on": "2026-10-27",
         "market": None}])  # no price at all -> null cell


@pytest.fixture
async def client(db):
    import httpx
    from app.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_price_matrix_shape_and_nulls(client, db):
    await _seed_matrix(db)
    r = await client.get("/api/cards/pokemon:m-1/price-matrix")
    assert r.status_code == 200
    m = r.json()
    assert m["grades"][:3] == ["raw", "PSA10", "PSA9"] and len(m["grades"]) == 31
    assert m["grades"][-1] == "CGC1" and m["base_currency"] == "EUR"
    assert {"pokemontcg", "pricecharting", "cardmarket", "altxyz", "manual", "tcgplayer"} <= set(m["sources"])
    assert set(m["cells"]) == set(m["grades"]) and all(set(row) == set(m["sources"]) for row in m["cells"].values())
    cm = m["cells"]["raw"]["cardmarket"]  # newest day; sold beats market; median used when no market
    assert (cm["kind"], cm["price"], cm["observed_on"], cm["sample_size"]) == ("sold", 90, "2026-10-27", 5)
    tp = m["cells"]["raw"]["tcgplayer"]  # first card variant wins, converted at 0.9; empty-price row ignored
    assert (tp["variant"], tp["price"], tp["currency"], tp["price_base"]) == ("holofoil", 2000, "USD", 1800)
    assert m["cells"]["PSA10"]["pricecharting"]["price"] == 5000
    assert m["cells"]["PSA9"]["pricecharting"] is None and m["cells"]["raw"]["altxyz"] is None
    assert m["cells"]["raw"]["pricecharting"] is None


async def test_price_matrix_unknown_card_404(client):
    assert (await client.get("/api/cards/nope/price-matrix")).status_code == 404


async def test_price_history_filters(client, db):
    await _seed_matrix(db)
    h = (await client.get("/api/cards/pokemon:m-1/prices",
                          params={"source": ["cardmarket", "tcgplayer"], "kind": "market", "days": 3650})).json()
    assert {p["source"] for p in h} == {"cardmarket", "tcgplayer"} and {p["kind"] for p in h} == {"market"}
    assert [p["observed_on"] for p in h] == sorted(p["observed_on"] for p in h)
    tp = next(p for p in h if p["source"] == "tcgplayer" and p["variant"] == "holofoil")
    assert tp["market_base"] == 1800 and tp["base_currency"] == "EUR"
    g = (await client.get("/api/cards/pokemon:m-1/prices", params={"grade_key": "PSA10"})).json()
    assert [p["source"] for p in g] == ["pricecharting"]
