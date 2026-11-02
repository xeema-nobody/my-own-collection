import httpx
import pytest
from pymongo.errors import DuplicateKeyError

from app.db.models import AlertIn, WishIn, WishPatch
from app.main import app
from app.services import alerts, price_fetch, wishlist
from tests.test_alerts import CID, events, set_price, setup


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


async def test_add_is_idempotent_and_priced(db):
    await setup(db, owned=False)                                  # 90.00 EUR market
    a = await wishlist.add(db, WishIn(card_id=CID, target_price=8000))
    b = await wishlist.add(db, WishIn(card_id=CID, target_price=7000, note="holo"))
    assert a["id"] == b["id"] and await db.wishlist.count_documents({}) == 1
    assert (b["target_price"], b["note"], b["value"], b["price_kind"]) == (7000, "holo", 9000, "market")
    assert b["gap"] == 2000 and b["hit"] is False and b["card"]["name"] == "Charizard"


async def test_unknown_card_404_and_unique_key(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        await wishlist.add(db, WishIn(card_id="pokemon:nope-1"))
    assert e.value.status_code == 404
    await setup(db, owned=False)
    await wishlist.add(db, WishIn(card_id=CID))
    with pytest.raises(DuplicateKeyError):
        await db.wishlist.insert_one({"wish_key": wishlist.make_wish_key(CID, None, None), "card_id": CID})


async def test_graded_want_without_graded_price_is_not_priced(db):
    await setup(db, owned=False)                                  # raw price only
    w = await wishlist.add(db, WishIn(card_id=CID, grading={"company": "PSA", "grade": 9, "cert_number": "123"},
                                      target_price=100))
    assert w["value"] is None and w["needs_price"] is True and w["hit"] is False and w["gap"] is None
    assert w["grading"]["cert_number"] is None                    # a want has no cert
    assert await alerts.evaluate(db) == 0                         # unknown never fires


async def test_hit_flag(db):
    await setup(db, owned=False)
    w = await wishlist.add(db, WishIn(card_id=CID, target_price=9500))
    assert w["hit"] is True and w["gap"] == -500


async def test_target_keeps_one_linked_rule(db):
    await setup(db, owned=False)
    w = await wishlist.add(db, WishIn(card_id=CID, target_price=8000))
    [r] = await db.alerts.find().to_list(None)
    assert (r["scope"], r["wish_id"], r["op"], r["threshold"], r["auto"]) == ("wish", w["id"], "below", 8000, True)
    await wishlist.patch(db, w["id"], WishPatch(target_price=9500))
    [r] = await db.alerts.find().to_list(None)
    assert r["threshold"] == 9500
    await wishlist.patch(db, w["id"], WishPatch(alert=False))
    assert await db.alerts.count_documents({}) == 0
    await wishlist.patch(db, w["id"], WishPatch(alert=True))
    assert await db.alerts.count_documents({}) == 1
    await wishlist.remove(db, w["id"])
    assert await db.alerts.count_documents({}) == 0 and await db.wishlist.count_documents({}) == 0


async def test_no_target_no_rule(db):
    await setup(db, owned=False)
    await wishlist.add(db, WishIn(card_id=CID))
    assert await db.alerts.count_documents({}) == 0


async def test_wish_alert_fires_once_rearms_and_total_ignores_wishlist(db):
    await setup(db, owned=False)                                  # nothing owned
    await wishlist.add(db, WishIn(card_id=CID, target_price=9500))   # 90.00 < 95.00
    await alerts.create(db, AlertIn(scope="total", op="above", threshold=100))
    assert await alerts.evaluate(db) == 1                         # only the wish rule: total has no rows
    assert await alerts.evaluate(db) == 0
    [e] = await events(db)
    assert (e["name"], e["value"], e["card_id"]) == ("Charizard", 9000, CID)
    await set_price(db, 12000)                                    # 108.00: clears
    await alerts.evaluate(db)
    assert (await db.alerts.find_one({"scope": "wish"}))["triggered"] is False
    await set_price(db, 9000)                                     # 81.00: fires again
    assert await alerts.evaluate(db) == 1


async def test_wish_pct_rule_and_validation(db):
    await setup(db, owned=False)
    w = await wishlist.add(db, WishIn(card_id=CID))
    r = await alerts.create(db, AlertIn(scope="wish", wish_id=w["id"], op="down_pct", threshold=10, days=7))
    assert r["description"].startswith("Wishlist Charizard")
    await alerts.evaluate(db)                                     # no past price: unknown, no crash
    assert (await db.alerts.find_one())["triggered"] is False
    with pytest.raises(ValueError):
        AlertIn(scope="wish", op="below", threshold=100)          # no wish_id
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await alerts.create(db, AlertIn(scope="wish", wish_id="ffffffffffffffffffffffff", op="below", threshold=1))


async def test_api_and_card_flag(db, client):
    await setup(db, owned=False)
    r = await client.post("/api/wishlist", json={"card_id": CID, "target_price": 8000})
    assert r.status_code == 201
    wid = r.json()["id"]
    assert (await client.get("/api/wishlist")).json()[0]["id"] == wid
    assert (await client.get("/api/wishlist", params={"card_id": "other"})).json() == []
    cards = (await client.get("/api/cards")).json()["items"]
    assert [c["wished"] for c in cards] == [True]
    assert (await client.patch(f"/api/wishlist/{wid}", json={"note": "x"})).json()["note"] == "x"
    assert (await client.delete(f"/api/wishlist/{wid}")).status_code == 204
    assert (await client.delete(f"/api/wishlist/{wid}")).status_code == 404
    assert (await client.post("/api/wishlist", json={"card_id": "nope"})).status_code == 404
    assert (await client.post("/api/wishlist", json={"card_id": CID, "target_price": 0})).status_code == 422
    assert (await client.get("/api/cards")).json()["items"][0]["wished"] is False


async def test_fetch_targets_include_wishlist(db):
    await setup(db, owned=False)
    await wishlist.add(db, WishIn(card_id=CID))
    assert await price_fetch.resolve_targets(db, wishlist=True) == [CID]
    assert await price_fetch.stalest_owned(db, 5) == [CID]
