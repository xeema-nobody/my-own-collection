from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.db.models import AlertIn
from app.main import app
from app.services import alerts
from app.services import snapshots
from app.services.pricing import get_rates, store_card_prices, store_scraped_points
from tests.conftest import make_card

UTC = timezone.utc
CID = "pokemon:a-1"


def day(n=0):
    return (datetime.now(UTC) - timedelta(days=n)).strftime("%Y-%m-%d")


def pt(cents, grade="raw", kind="market", source="pricecharting"):
    return {"source": source, "kind": kind, "grade_key": grade, "variant": None, "currency": "USD",
            "market": cents, "as_of": None}


async def setup(db, usd_cents=10000, owned=True, qty=1):
    """Card priced by pricecharting (preferred) at `usd_cents` x 0.9 EUR; one raw NM stack."""
    doc = make_card("a", "1")
    await db.cards.insert_one(doc)
    await store_card_prices(db, doc, await get_rates(db))
    if usd_cents is not None:
        await store_scraped_points(db, CID, [pt(usd_cents)], day())
    if not owned:
        return None
    r = await db.collection_items.insert_one({
        "card_id": CID, "variant": None, "language": "en", "condition": "NM", "grading": None,
        "quantity": qty, "stack_key": f"k{qty}", "created_at": datetime.now(UTC)})
    return str(r.inserted_id)


async def rule(db, **kw):
    body = {"scope": "total", "op": "above", "threshold": 5000, **kw}
    return await alerts.create(db, AlertIn(**body))


async def set_price(db, usd_cents, observed_on=None):
    await store_scraped_points(db, CID, [pt(usd_cents)], observed_on or day())


async def events(db):
    return await db.alert_events.find({"type": "alert"}).to_list(None)


async def test_above_fires_once_rearms_and_fires_again(db):
    item = await setup(db)                      # 90.00 EUR
    r = await rule(db, scope="stack", item_id=item, threshold=5000)
    assert await alerts.evaluate(db) == 1
    assert await alerts.evaluate(db) == 0       # same crossing: no second event
    [e] = await events(db)
    assert (e["value"], e["name"], e["read"], e["price_kind"]) == (9000, "Charizard", False, "market")
    await set_price(db, 4000)                   # 36.00: clears, re-arms
    assert await alerts.evaluate(db) == 0
    assert (await db.alerts.find_one())["triggered"] is False
    await set_price(db, 12000)
    assert await alerts.evaluate(db) == 1
    assert len(await events(db)) == 2 and r["description"].startswith("Stack Charizard")


async def test_below_and_double_evaluate_is_idempotent(db):
    await setup(db)
    await rule(db, op="below", threshold=9500)
    assert await alerts.evaluate(db) == 1
    assert await alerts.evaluate(db) == 0
    assert len(await events(db)) == 1


async def test_estimated_skipped_unless_included(db):
    await setup(db, usd_cents=None)             # catalog prices only
    await db.collection_items.update_one({}, {"$set": {"grading": {"company": "PSA", "grade": 9, "cert_number": None},
                                                       "condition": None}})
    rid = (await rule(db, op="above", threshold=100))["id"]
    assert await alerts.evaluate(db) == 0       # raw fallback = estimated
    assert (await db.alerts.find_one())["triggered"] is False and (await db.alerts.find_one())["last_value"] is None
    await alerts.patch(db, rid, alerts.AlertPatch(include_estimated=True))
    assert await alerts.evaluate(db) == 1
    [e] = await events(db)
    assert e["estimated"] is True


async def test_unknown_leaves_state_untouched(db):
    await setup(db)
    await rule(db, threshold=5000)
    await alerts.evaluate(db)
    assert (await db.alerts.find_one())["triggered"] is True
    await db.prices.delete_many({})
    await db.cards.update_one({"_id": CID}, {"$set": {"latest_price": {}}})
    await alerts.evaluate(db)                   # unpriced: neither cleared nor re-fired
    assert (await db.alerts.find_one())["triggered"] is True
    assert len(await events(db)) == 1


async def test_kind_filter(db):
    await setup(db)                             # market price
    await rule(db, kind="sold", threshold=100)
    assert await alerts.evaluate(db) == 0
    await rule(db, kind="market", threshold=100)
    assert await alerts.evaluate(db) == 1


async def test_percent_over_days_uses_past_valuation(db):
    await setup(db, usd_cents=10000)
    await set_price(db, 10000, day(3))          # 3 d ago 90.00 EUR
    await set_price(db, 12000, day())           # now 108.00 EUR = +20 %
    await rule(db, op="up_pct", threshold=10, days=2)
    await rule(db, op="down_pct", threshold=10, days=2)
    assert await alerts.evaluate(db) == 1
    [e] = await events(db)
    assert (e["prev"], e["value"], e["pct"]) == (9000, 10800, 20.0)


async def test_card_and_total_scope_sum_stacks(db):
    await setup(db, qty=2)
    await db.collection_items.insert_one({"card_id": CID, "variant": None, "language": "ja", "condition": "NM",
                                          "grading": None, "quantity": 1, "stack_key": "other",
                                          "created_at": datetime.now(UTC)})
    await rule(db, scope="card", card_id=CID, threshold=26000)      # 3 x 90.00 = 270.00
    await rule(db, scope="total", threshold=27000)                  # not above
    assert await alerts.evaluate(db) == 1
    [e] = await events(db)
    assert e["value"] == 27000 and e["card_id"] == CID


async def test_snapshot_runs_alerts_and_survives_failure(db, monkeypatch):
    await setup(db)
    await rule(db, threshold=5000)
    await snapshots.take_snapshot(db)
    assert len(await events(db)) == 1

    async def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(alerts, "evaluate", boom)
    assert (await snapshots.take_snapshot(db))["item_count"] == 1


async def test_system_event_dedupes_by_key(db):
    assert await alerts.notify_system(db, "fetch_skipped:d", "fetcher down") is True
    assert await alerts.notify_system(db, "fetch_skipped:d", "fetcher down") is False
    assert await alerts.unread_count(db) == 1


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


async def test_api_crud_events_and_validation(db, client):
    item = await setup(db)
    bad = [{"scope": "stack", "op": "above", "threshold": 100},              # no item_id
           {"scope": "total", "op": "up_pct", "threshold": 5},               # no days
           {"scope": "total", "op": "above", "threshold": -1},
           {"scope": "total", "op": "sideways", "threshold": 1},
           {"scope": "total", "op": "above", "threshold": 10.5}]
    for b in bad:
        assert (await client.post("/api/alerts", json=b)).status_code == 422
    assert (await client.post("/api/alerts", json={"scope": "stack", "item_id": "ffffffffffffffffffffffff",
                                                   "op": "above", "threshold": 1})).status_code == 404
    r = await client.post("/api/alerts", json={"scope": "stack", "item_id": item, "op": "above", "threshold": 5000})
    assert r.status_code == 201
    rid = r.json()["id"]
    assert (await client.post("/api/alerts/evaluate")).json() == {"fired": 1}
    assert (await client.get("/api/alerts/unread-count")).json() == {"count": 1}
    [ev] = (await client.get("/api/alerts/events", params={"unread": True})).json()
    assert ev["rule"].startswith("Stack Charizard #1")
    assert (await client.post("/api/alerts/events/read", json={"ids": [ev["id"]]})).json() == {"marked": 1}
    assert (await client.get("/api/alerts/unread-count")).json() == {"count": 0}
    assert (await client.patch(f"/api/alerts/{rid}", json={"enabled": False})).json()["enabled"] is False
    assert (await client.get("/api/alerts")).json()[0]["id"] == rid
    assert (await client.delete(f"/api/alerts/{rid}")).status_code == 204
    assert (await client.delete(f"/api/alerts/{rid}")).status_code == 404


async def _ev(db, age_days, read):
    await db.alert_events.insert_one({"type": "alert", "rule": "r", "read": read,
                                      "fired_at": datetime.now(UTC) - timedelta(days=age_days)})


async def test_prune_deletes_only_old_read_events(db):
    await _ev(db, 120, True)      # old + read: pruned
    await _ev(db, 120, False)     # old + unread: kept
    await _ev(db, 10, True)       # recent + read: kept
    assert await alerts.prune_events(db, keep_days=90) == 1
    left = [(e["read"]) async for e in db.alert_events.find()]
    assert sorted(left) == [False, True]
    assert await alerts.prune_events(db, keep_days=90) == 0     # idempotent


async def test_prune_zero_days_disables(db):
    await _ev(db, 999, True)
    assert await alerts.prune_events(db, keep_days=0) == 0
    assert await db.alert_events.count_documents({}) == 1


async def test_prune_defaults_to_setting(db, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "alert_events_keep_days", 5)
    await _ev(db, 6, True)
    assert await alerts.prune_events(db) == 1
