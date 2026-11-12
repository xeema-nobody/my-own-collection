from datetime import datetime, timezone

import httpx
import pytest

from app.db.models import AlertIn, SealedIn
from app.main import app
from app.services import alerts, collection as coll, sealed
from app.services.pricing import store_scraped_points
from tests.conftest import make_card
from tests.test_alerts import day, pt
from tests.test_sealed import BOX, seed_set

PULL = "pokemon:sv3-1"


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


async def box(db, qty=3, cost=12000):
    await seed_set(db)
    await db.cards.insert_one(make_card("sv3", "1"))
    return await sealed.add(db, SealedIn(**BOX, quantity=qty, acquired={"type": "purchased", "price": cost}))


async def test_open_partial_logs_exit_and_opening(db, client):
    s = await box(db)
    r = await client.post(f"/api/collection/{s['id']}/open", json={"quantity": 1, "extras": "code card, coin", "note": "pack 1"})
    assert r.status_code == 201
    j = r.json()
    assert (j["opened"], j["left"], j["stack_deleted"], j["pulled"]) == (1, 2, False, [])
    [ex] = (await client.get("/api/collection/exits")).json()
    assert ex["reason"] == "opened" and ex["opening_id"] == j["opening_id"] and ex["acquired"]["price"] == 12000
    op = (await client.get(f"/api/openings/{j['opening_id']}")).json()
    assert op["extras"] == "code card, coin" and op["quantity"] == 1 and op["pulls"] == []
    assert (await db.collection_items.find_one({}))["quantity"] == 2


async def test_open_all_units_deletes_stack_and_clamps(db, client):
    s = await box(db, qty=2)
    j = (await client.post(f"/api/collection/{s['id']}/open", json={"quantity": 9})).json()
    assert (j["opened"], j["stack_deleted"]) == (2, True) and await db.collection_items.count_documents({}) == 0


async def test_only_sealed_can_be_opened(db, client):
    await db.cards.insert_one(make_card("a", "1"))
    r = await db.collection_items.insert_one({"stack_key": "k", "card_id": "pokemon:a-1", "language": "en", "condition": "NM",
                                              "grading": None, "quantity": 1, "created_at": datetime.now(timezone.utc)})
    assert (await client.post(f"/api/collection/{r.inserted_id}/open", json={})).status_code == 400
    assert await db.openings.count_documents({}) == 0 and await db.collection_items.count_documents({}) == 1


async def test_pulled_cards_are_linked_costless_and_count_in_value(db, client):
    s = await box(db)
    await store_scraped_points(db, PULL, [pt(10000)], day())
    j = (await client.post(f"/api/collection/{s['id']}/open", json={
        "quantity": 1, "date": "2026-11-12", "pulled": [{"card_id": PULL, "quantity": 2}]})).json()
    [p] = j["pulled"]
    st = await db.collection_items.find_one({"card_id": PULL})
    assert st["quantity"] == 2 and st["acquired"]["type"] == "pulled" and st["acquired"]["price"] is None
    assert st["acquired"]["date"] == "2026-11-12" and st["acquired"]["source"].startswith("opened: ")
    [v] = await coll.valuate(db)
    assert v["value"] == 2 * 9000 and v["cost"] is None            # in collection value, no cost => out of P/L
    op = (await client.get("/api/openings")).json()[0]
    assert op["pulls"][0]["stack_id"] == p["stack_id"] and op["pulls"][0]["name"]


async def test_later_pulls_and_merge_into_bought_stack_keeps_cost(db, client):
    s = await box(db)
    await db.collection_items.insert_one({"stack_key": f"{PULL}||en|NM|||", "card_id": PULL, "variant": None, "language": "en",
                                          "condition": "NM", "grading": None, "quantity": 1,
                                          "acquired": {"type": "purchased", "price": 300, "currency": "EUR"},
                                          "created_at": datetime.now(timezone.utc)})
    j = (await client.post(f"/api/collection/{s['id']}/open", json={})).json()
    r = await client.post(f"/api/openings/{j['opening_id']}/pulls", json={"pulled": [{"card_id": PULL}]})
    assert r.status_code == 201 and r.json()["pulled"][0]["type_conflict"] is True
    st = await db.collection_items.find_one({"card_id": PULL})
    assert st["quantity"] == 2 and st["acquired"]["price"] == 300 and st["acquired"]["type"] == "purchased"
    assert len((await client.get(f"/api/openings/{j['opening_id']}")).json()["pulls"]) == 1


async def test_bad_pulls_change_nothing(db, client):
    s = await box(db)
    r = await client.post(f"/api/collection/{s['id']}/open", json={"pulled": [{"card_id": "pokemon:nope-1"}]})
    assert r.status_code == 404
    r = await client.post(f"/api/collection/{s['id']}/open", json={"pulled": [{"card_id": s["card_id"]}]})
    assert r.status_code == 400
    assert (await db.collection_items.find_one({}))["quantity"] == 3 and await db.openings.count_documents({}) == 0
    assert (await client.post("/api/openings/zzz/pulls", json={"pulled": [{"card_id": PULL}]})).status_code == 404


async def test_alerts_fire_on_sealed_stack_but_total_ignores_it(db):
    s = await box(db, qty=1)
    await store_scraped_points(db, s["card_id"], [pt(36893)], day())      # 332 EUR
    stack = await alerts.create(db, AlertIn(scope="stack", item_id=s["id"], op="above", threshold=10000))
    card = await alerts.create(db, AlertIn(scope="card", card_id=s["card_id"], op="above", threshold=10000))
    total = await alerts.create(db, AlertIn(scope="total", op="above", threshold=10000))
    assert stack["label"] == "Obsidian Flames Booster Box"                 # no trailing '#'
    assert await alerts.evaluate(db) == 2
    fired = {e["rule_id"] async for e in db.alert_events.find()}
    assert fired == {stack["id"], card["id"]} and total["id"] not in fired
