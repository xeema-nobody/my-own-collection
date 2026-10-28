from datetime import datetime, timedelta, timezone

from app.services.movers import movers
from app.services.pricing import store_scraped_points, today
from test_valuation import CID, card, item, pt, sale

UTC = timezone.utc


def day(n: int) -> str:
    return (datetime.now(UTC) - timedelta(days=n)).strftime("%Y-%m-%d")


async def own(db, it):
    await db.collection_items.insert_one(it)


async def test_graded_mover_is_sold_based(db):
    await card(db)
    for c in (4000, 4000, 4000):
        await sale(db, "PSA9", c, days_ago=20)  # old sales only
    for c in (6000, 6000, 6000, 6000):
        await sale(db, "PSA9", c, days_ago=1)  # median of last 10 sales (7) = 6000 vs 4000 a week ago
    await own(db, item(9))
    res = await movers(db, days=7)
    [up] = res["up"]
    assert (up["kind"], up["grade_key"], up["match"]) == ("sold", "PSA9", "exact")
    assert up["pct"] == 50.0 and res["down"] == []


async def test_raw_mover_uses_observation_log(db):
    await card(db)
    await store_scraped_points(db, CID, [pt("pricecharting", "raw", 1000)], observed_on=day(10))
    await store_scraped_points(db, CID, [pt("pricecharting", "raw", 2000)], observed_on=today())
    await own(db, item())
    res = await movers(db, days=7)
    assert [m["pct"] for m in res["up"]] == [100.0]


async def test_changed_fallback_is_not_a_move(db):
    await card(db)  # only raw prices: PSA9 item values via raw_fallback now and then
    await own(db, item(9))
    await store_scraped_points(db, CID, [pt("pricecharting", "PSA9", 5000, "sold")], observed_on=today())
    res = await movers(db, days=7)  # then: raw_fallback, now: exact -> not comparable
    assert res == {"down": [], "up": []}


async def test_no_history_no_movers(db):
    await card(db)
    await own(db, item())
    assert await movers(db, days=7) == {"down": [], "up": []}
