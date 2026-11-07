from datetime import datetime, timezone

import httpx
import pytest

from app.main import app
from tests.conftest import make_card

CID = "pokemon:a-1"


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


async def stack(db, qty=3, cost=500):
    await db.cards.insert_one(make_card("a", "1"))
    r = await db.collection_items.insert_one({
        "stack_key": "k", "card_id": CID, "variant": None, "language": "en", "condition": "NM", "grading": None,
        "quantity": qty, "acquired": {"type": "purchased", "price": cost, "currency": "EUR"},
        "created_at": datetime.now(timezone.utc)})
    return str(r.inserted_id)


async def test_partial_sold_keeps_stack_and_logs_price_and_cost(db, client):
    sid = await stack(db)
    r = await client.post(f"/api/collection/{sid}/remove", json={"quantity": 1, "reason": "sold", "price": 1200})
    assert r.json() == {"deleted": False, "quantity": 2, "removed": 1}
    ex = (await client.get("/api/collection/exits")).json()
    assert len(ex) == 1 and ex[0]["reason"] == "sold" and ex[0]["price"] == 1200
    assert ex[0]["acquired"]["price"] == 500 and ex[0]["card"]["name"]  # cost basis survives


async def test_full_remove_deletes_and_gift_ignores_price(db, client):
    sid = await stack(db, qty=1)
    r = await client.post(f"/api/collection/{sid}/remove", json={"reason": "gifted", "price": 999})
    assert r.json()["deleted"] is True and await db.collection_items.count_documents({}) == 0
    assert (await client.get("/api/collection/exits")).json()[0]["price"] is None


async def test_more_than_owned_clamps_and_unknown_404(db, client):
    sid = await stack(db, qty=2)
    r = await client.post(f"/api/collection/{sid}/remove", json={"quantity": 9})
    assert r.json()["removed"] == 2 and r.json()["deleted"] is True
    assert (await client.post(f"/api/collection/{sid}/remove", json={})).status_code == 404


async def test_delete_is_logged_not_silent(db, client):
    sid = await stack(db, qty=4)
    assert (await client.delete(f"/api/collection/{sid}")).status_code == 204
    ex = (await client.get("/api/collection/exits")).json()
    assert ex[0]["quantity"] == 4 and ex[0]["reason"] == "removed"
    assert (await client.delete(f"/api/collection/{sid}")).status_code == 404


async def test_bad_reason_rejected(db, client):
    sid = await stack(db)
    assert (await client.post(f"/api/collection/{sid}/remove", json={"reason": "stolen"})).status_code == 422


async def test_bulk_remove_logs_each_stack_and_reports_bad_ids(db, client):
    a = await stack(db, qty=3)
    r2 = await db.collection_items.insert_one({"stack_key": "k2", "card_id": CID, "variant": None, "language": "en",
        "condition": "LP", "grading": None, "quantity": 2, "acquired": None, "created_at": datetime.now(timezone.utc)})
    b = str(r2.inserted_id)
    r = await client.post("/api/collection/bulk-remove", json={"ids": [a, b, "nope", "0" * 24, a], "reason": "gifted", "note": "to a friend"})
    out = r.json()
    assert (out["removed"], out["copies"], out["failed"]) == (2, 5, 2)
    assert [x["ok"] for x in out["results"]] == [True, True, False, False]  # duplicate id counted once
    assert await db.collection_items.count_documents({}) == 0
    ex = (await client.get("/api/collection/exits")).json()
    assert len(ex) == 2 and {e["reason"] for e in ex} == {"gifted"} and {e["quantity"] for e in ex} == {3, 2}


async def test_bulk_remove_needs_ids(client):
    assert (await client.post("/api/collection/bulk-remove", json={"ids": []})).status_code == 422
    assert (await client.post("/api/collection/bulk-remove", json={"ids": ["x"], "reason": "stolen"})).status_code == 422


async def test_wishlist_bulk_remove_drops_alerts(db, client):
    await db.cards.insert_one(make_card("a", "1"))
    ids = []
    for k in ("w1", "w2"):
        ids.append(str((await db.wishlist.insert_one({"card_id": CID, "wish_key": k, "created_at": datetime.now(timezone.utc)})).inserted_id))
    await db.alerts.insert_one({"scope": "wish", "wish_id": ids[0]})
    r = await client.post("/api/wishlist/bulk-remove", json={"ids": ids + ["bad"]})
    assert (r.json()["removed"], r.json()["failed"]) == (2, 1)
    assert await db.wishlist.count_documents({}) == 0 and await db.alerts.count_documents({}) == 0
