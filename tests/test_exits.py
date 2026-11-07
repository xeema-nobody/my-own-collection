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
