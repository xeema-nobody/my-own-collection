from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import settings
from app.main import app
from app.services import reprice
from tests.test_listing_pack import stack


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


async def listed(client, sid, price=1000, platforms=("vinted",), listed_at="2026-11-01"):
    ls = [{"platform": p, "asking_price": price, "currency": "EUR", "listed_at": listed_at, "url": "https://www.vinted.nl/items/1-x"}
          for p in platforms]
    r = await client.put(f"/api/collection/{sid}/sale", json={"status": "listed", "listings": ls})
    assert r.status_code == 200, r.text


async def rows(client):
    r = await client.get("/api/reprice")
    assert r.status_code == 200, r.text
    return r.json()


def test_suggested_markup_rounding_and_none():
    assert reprice.suggested(1000) == 1100
    assert reprice.suggested(333, 10) == 366
    assert reprice.suggested(1000, 0) == 1000
    assert reprice.suggested(None) is None


async def test_table_market_change_and_suggested(db, client):
    sid = await stack(db, "1")
    await listed(client, sid, price=1000)
    t = await rows(client)
    assert t["markup_pct"] == 10 and len(t["rows"]) == 1
    r = t["rows"][0]
    assert r["market"] and r["suggested"] == round(r["market"] * 1.1)
    assert r["change_amount"] == r["market"] - 1000 and r["change_pct"] == round((r["market"] - 1000) / 10, 1)
    assert r["needs_platform_update"] is False and r["grade_key"] == "raw"


async def test_unpriced_stack_has_no_suggestion_never_zero(db, client):
    sid = await stack(db, "2", priced=False)
    await listed(client, sid, price=500)
    r = (await rows(client))["rows"][0]
    assert r["market"] is None and r["suggested"] is None and r["change_pct"] is None
    assert "no market price" in r["warnings"]


async def test_confirm_saves_price_flags_keeps_other_listing(db, client):
    sid = await stack(db, "3")
    await listed(client, sid, price=1000, platforms=("vinted", "ebay"))
    r = await client.post("/api/reprice/confirm", json={"item_id": sid, "platform": "vinted", "asking_price": 1234})
    assert r.status_code == 200, r.text
    ls = {l["platform"]: l for l in r.json()["sale"]["listings"]}
    assert ls["vinted"]["asking_price"] == 1234 and ls["vinted"]["needs_platform_update"] is True
    assert ls["vinted"]["listed_at"] == "2026-11-01"
    assert ls["ebay"]["asking_price"] == 1000 and ls["ebay"]["needs_platform_update"] is False
    assert (await client.post("/api/reprice/confirm", json={"item_id": sid, "platform": "marktplaats", "asking_price": 5})).status_code == 404
    assert (await client.post("/api/reprice/confirm", json={"item_id": sid, "platform": "vinted", "asking_price": 0})).status_code == 422


async def test_flag_cleared_when_vinted_update_published(db, client, tmp_path, monkeypatch):
    from app.services import publish_queue
    sid = await stack(db, "4")
    await listed(client, sid, price=1000)
    await client.post("/api/reprice/confirm", json={"item_id": sid, "platform": "vinted", "asking_price": 1500})
    await db.publish_queue.insert_one({"item_id": sid, "card_id": "pokemon:a-4", "state": "publishing", "mode": "update",
                                       "url": "https://www.vinted.nl/items/1-x", "created_at": datetime.now(timezone.utc),
                                       "payload": {"price": 1500, "currency": "EUR"}})
    qid = str((await db.publish_queue.find_one({"item_id": sid}))["_id"])
    from app.db.models import PublishResultIn
    await publish_queue.report(db, qid, PublishResultIn(state="published", url="https://www.vinted.nl/items/1-x"))
    r = (await rows(client))["rows"][0]
    assert r["needs_platform_update"] is False and r["asking_price"] == 1500


async def _comp(db, card_id, grade_key, price, days_ago=1, source="altxyz", lid="a"):
    now = datetime.now(timezone.utc)
    r = await db.sales.insert_one({"card_id": card_id, "source": source, "listing_id": lid, "grade_key": grade_key, "price": price,
                                   "currency": "EUR", "sold_at": (now - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0),
                                   "kind": "sold", "first_seen": now})
    return str(r.inserted_id)


async def test_sold_comps_match_grade_ignore_older_than_listing_and_dedupe(db, client):
    raw = await stack(db, "5")
    slab = await stack(db, "6", grading={"company": "PSA", "grade": 9}, key="slab6")
    await listed(client, raw, listed_at=(datetime.now(timezone.utc) - timedelta(days=5)).date().isoformat())
    await listed(client, slab, listed_at=(datetime.now(timezone.utc) - timedelta(days=5)).date().isoformat())
    await _comp(db, "pokemon:a-5", "raw", 300, lid="r1")
    await _comp(db, "pokemon:a-5", "raw", 250, days_ago=30, lid="r-old")        # before listing
    await _comp(db, "pokemon:a-5", "PSA9", 9000, lid="wrong-grade")             # other grade
    await _comp(db, "pokemon:a-6", "PSA9", 8000, lid="s1")
    out = await reprice.evaluate(db)
    assert out["sold_comps"] == 2
    ev = [e async for e in db.alert_events.find({"type": "sold_comp"})]
    assert {e["card_id"] for e in ev} == {"pokemon:a-5", "pokemon:a-6"}
    assert any("condition unknown" in e["rule"] for e in ev if e["card_id"] == "pokemon:a-5")
    again = await reprice.evaluate(db)
    assert again["sold_comps"] == 0                                              # idempotent
    await _comp(db, "pokemon:a-6", "PSA9", 7900, lid="s2")
    assert (await reprice.evaluate(db))["sold_comps"] == 1                      # only the new comp


async def test_price_move_event_once_per_day_and_threshold(db, client, monkeypatch):
    sid = await stack(db, "7")
    await listed(client, sid, price=1000)
    market = (await rows(client))["rows"][0]["market"]
    await listed(client, sid, price=market)                                     # asking == market: no move
    assert (await reprice.evaluate(db))["price_moves"] == 0
    await listed(client, sid, price=max(1, round(market * 0.5)))               # far below market
    assert (await reprice.evaluate(db))["price_moves"] == 1
    assert (await reprice.evaluate(db))["price_moves"] == 0                     # same day: deduped
    ev = await db.alert_events.find_one({"type": "reprice"})
    assert "above your asking" in ev["rule"] and ev["pct"] > 5


async def test_evaluate_endpoint_and_no_listed_stacks(db, client):
    r = await client.post("/api/reprice/evaluate")
    assert r.status_code == 200 and r.json() == {"price_moves": 0, "sold_comps": 0}
    assert (await rows(client))["rows"] == []
