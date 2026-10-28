from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from app.main import app
from app.providers.price import pricecharting
from app.providers.price.base import AdapterResult, Sale
from app.services import price_fetch as pf
from app.services.pricing import store_scraped_points
from app.services.sales import store_chart_seed, store_sales
from tests.test_price_fetch import FakeClient, FakeProvider, PC_URL, providers, pt, seed

FIXTURE = Path(__file__).parent / "fixtures/pricecharting/product_mew_ex_205.html"
CID = "pokemon:sv3pt5-1"


def sale(lid, grade="PSA9", price=5000, source="altxyz", on=date(2026, 10, 1)):
    return Sale(source, lid, grade, price, "USD", on, f"title {lid}")


async def test_store_sales_dedupes_and_adds_new(db):
    assert await store_sales(db, CID, [sale("a"), sale("b", "raw", 900)]) == 2
    assert await store_sales(db, CID, [sale("a"), sale("b", "raw", 900)]) == 0
    assert await store_sales(db, CID, [sale("a"), sale("c")]) == 1
    assert await store_sales(db, CID, []) == 0
    assert await db.sales.count_documents({}) == 3
    row = await db.sales.find_one({"listing_id": "a"})
    assert row["sold_at"] == datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert row["kind"] == "sold" and row["created_by"] == "scraper" and row["grade_key"] == "PSA9"


async def test_same_listing_other_source_or_card_is_distinct(db):
    await store_sales(db, CID, [sale("a")])
    await store_sales(db, CID, [sale("a", source="pricecharting")])
    await store_sales(db, "pokemon:sv3pt5-2", [sale("a")])
    assert await db.sales.count_documents({}) == 3


async def test_manual_sales_unconstrained_by_listing_index(db):
    for _ in range(2):
        await db.sales.insert_one({"card_id": CID, "source": "manual", "grade_key": "raw", "price": 1,
                                   "currency": "USD", "sold_at": datetime.now(timezone.utc)})
    assert await db.sales.count_documents({}) == 2


async def test_card_detail_stats_include_scraped(db):
    [c] = await seed(db, "1")
    await store_sales(db, c, [sale("a", price=4000, on=datetime.now(timezone.utc).date()),
                              sale("b", price=6000, on=datetime.now(timezone.utc).date())])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as http:
        d = (await http.get(f"/api/cards/{c}")).json()
    assert len(d["sales"]) == 2
    [st] = d["sales_stats"]
    assert (st["source"], st["grade_key"], st["count"], st["avg"]) == ("altxyz", "PSA9", 2, 5000)


async def test_chart_seed_idempotent_and_flagged(db):
    chart = [(date(2026, 8, 1), 2409), (date(2026, 9, 1), 2653)]
    assert await store_chart_seed(db, CID, "pricecharting", chart) == 2
    assert await store_chart_seed(db, CID, "pricecharting", chart) == 0
    assert await store_chart_seed(db, CID, "pricecharting", []) == 0
    row = await db.prices.find_one({"observed_on": "2026-08-01"})
    assert row["seed"] is True and row["market"] == 2409 and row["grade_key"] == "raw"
    assert row["as_of"] == datetime(2026, 8, 1, tzinfo=timezone.utc)


async def test_seed_never_overwrites_real_and_real_clears_seed(db):
    [c] = await seed(db, "1")
    d = datetime.now(timezone.utc).date()
    await store_scraped_points(db, c, [pt("pricecharting", market=7777)])
    assert await store_chart_seed(db, c, "pricecharting", [(d, 1111)]) == 0
    assert (await db.prices.find_one({"observed_on": d.isoformat()}))["market"] == 7777
    # seed first, then a real observation the same day replaces it and drops the flag
    await db.prices.delete_many({})
    await store_chart_seed(db, c, "pricecharting", [(d, 1111)])
    await store_scraped_points(db, c, [pt("pricecharting", market=7777)])
    row = await db.prices.find_one({"observed_on": d.isoformat()})
    assert row["market"] == 7777 and "seed" not in row


async def test_seed_visible_in_price_history_not_latest(db):
    [c] = await seed(db, "1")
    await store_chart_seed(db, c, "pricecharting", [(date(2026, 8, 1), 2409)])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as http:
        rows = (await http.get(f"/api/cards/{c}/prices", params={"source": "pricecharting", "days": 3650})).json()
    assert [r["market"] for r in rows] == [2409] and rows[0]["seed"] is True
    assert "pricecharting" not in ((await db.cards.find_one({"_id": c})).get("latest_price") or {})


async def test_fetch_prices_stores_sales_and_chart(db):
    [c] = await seed(db, "1")
    res = AdapterResult("ok", points=[pt("pricecharting")], url=PC_URL,
                        sales=[sale("a", source="pricecharting"), sale("b", source="pricecharting")],
                        chart=[(date(2026, 8, 1), 2409)])
    p = FakeProvider("pricecharting", default=res)
    kw = dict(provider_for=providers(pricecharting=p), client=FakeClient())
    s1 = await pf.fetch_prices([c], ["pricecharting"], **kw)
    assert (s1["sales_new"], s1["seeded"]) == (2, 1)
    s2 = await pf.fetch_prices([c], ["pricecharting"], force=True, **kw)
    assert (s2["sales_new"], s2["seeded"]) == (0, 0)


async def test_pricecharting_fixture_roundtrip(db):
    res = pricecharting.parse_product(FIXTURE.read_text(), PC_URL, date(2026, 10, 27))
    ids = {s.listing_id for s in res.sales}
    assert ids and res.chart
    assert await store_sales(db, CID, res.sales) == len(ids)
    assert await store_sales(db, CID, res.sales) == 0
    assert await store_chart_seed(db, CID, "pricecharting", res.chart) == len({d for d, _ in res.chart})
