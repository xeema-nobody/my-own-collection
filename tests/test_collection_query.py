from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.config import settings
from app.main import app
from app.services import acquisition, valuation_cache
from app.services import collection as coll
from app.services import collection_query as cq
from app.services.pricing import get_rates, store_card_prices
from tests.conftest import make_card


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


NOW = datetime.now(timezone.utc)


async def stack(db, card, key, qty=1, grade=None, company="PSA", lang="en", cond="NM", acq=None, age=0):
    await db.collection_items.insert_one({
        "stack_key": key, "card_id": card["_id"], "variant": None, "language": lang, "quantity": qty,
        "condition": None if grade else cond, "created_at": NOW - timedelta(days=age),
        "grading": {"company": company, "grade": grade, "cert_number": None} if grade else None,
        "acquired": acq})


@pytest.fixture
async def world(db):
    """a-1 (set a, priced), b-2 (set b, Rare Holo -> change rarity, priced), c-3 (no price)."""
    a, b, c = make_card("a", "1"), make_card("b", "2"), make_card("c", "3", priced=False)
    a.update(name="Alakazam", name_norm="alakazam", search_text="alakazam 1")
    b.update(name="Blastoise", name_norm="blastoise", search_text="blastoise 2", rarity="Rare", types=["Water"])
    c.update(name="Cubone", name_norm="cubone", search_text="cubone 3")
    for d in (a, b, c):
        await db.cards.insert_one(d)
    rates = await get_rates(db)
    for d in (a, b):
        await store_card_prices(db, d, rates)
    await stack(db, a, "a-raw", qty=2, acq={"type": "purchased", "price": 100, "currency": "EUR"}, age=3)
    await stack(db, a, "a-psa", grade=9, acq={"type": "pulled", "price": 0, "currency": "EUR"}, age=2)
    await stack(db, b, "b-raw", lang="ja", cond="LP", acq={"type": "purchased", "price": 999999, "currency": "EUR"}, age=1)
    await stack(db, c, "c-raw")
    return db


def ids(r):
    return [i["card_id"].split(":")[1][0] + ("/g" if i["grading"] else "") for i in r["items"]]


async def get(client, qs=""):
    r = await client.get("/api/collection" + qs)
    assert r.status_code == 200, r.text
    return r.json()


async def test_plain_filters(world, client):
    assert (await get(client))["total"] == 4
    assert (await get(client, "?set=b"))["total"] == 1  # set id is the card's set.id
    assert (await get(client, "?rarity=Rare"))["total"] == 1
    assert (await get(client, "?type=Water"))["total"] == 1
    assert (await get(client, "?language=ja"))["total"] == 1
    assert (await get(client, "?condition=LP"))["total"] == 1
    assert (await get(client, "?graded=true"))["total"] == 1
    assert (await get(client, "?graded=false"))["total"] == 3
    assert (await get(client, "?grader=PSA"))["total"] == 1 and (await get(client, "?grader=BGS"))["total"] == 0
    assert (await get(client, "?grade=9"))["total"] == 1 and (await get(client, "?grade=9.5"))["total"] == 0
    assert (await get(client, "?q=blast"))["total"] == 1
    assert (await get(client, "?q=ala&graded=true"))["total"] == 1


async def test_acquisition_cost_and_needs_price_filters(world, client):
    assert (await get(client, "?acquisition=purchased"))["total"] == 2
    assert (await get(client, "?acquisition=pulled"))["total"] == 1
    assert (await get(client, "?acquisition=unset"))["total"] == 1
    assert (await get(client, "?cost_missing=true"))["total"] == 1
    assert (await get(client, "?cost_missing=false"))["total"] == 3
    assert (await get(client, "?needs_price=true"))["total"] == 1  # the slab has no graded price


async def test_pl_and_price_range_filters(world, client):
    # b-raw cost 9999.99 EUR >> value -> negative; a-raw cost 1 EUR x2 << value -> positive
    neg, pos = await get(client, "?pl=negative"), await get(client, "?pl=positive")
    assert ids(neg) == ["b"] and ids(pos) == ["a"]
    assert (await get(client, "?price_min=1"))["total"] == 2          # priced copies only
    assert (await get(client, "?price_min=999999999"))["total"] == 0
    assert (await get(client, "?price_max=999999999"))["total"] == 2  # unpriced never match a range


async def test_stale_filter(world, client, monkeypatch):
    assert (await get(client, "?stale=true"))["total"] == 0
    monkeypatch.setattr(settings, "market_max_age_days", 0)       # every upstream as_of is now "old"
    r = await get(client, "?stale=true")
    assert r["total"] == 2 and (await get(client, "?stale=false"))["total"] == 2   # the two priced raw stacks; slab + unpriced have no price to be stale


async def test_sort_keys_and_none_last(world, client):
    assert ids(await get(client, "?sort=name&order=asc")) == ["a", "a/g", "b", "c"]
    assert ids(await get(client, "?sort=name&order=desc"))[:2] == ["c", "b"]
    byval = ids(await get(client, "?sort=value"))
    assert set(byval[-2:]) == {"a/g", "c"}                                  # unvalued always last
    assert byval[0] in ("a", "b")
    asc = ids(await get(client, "?sort=value&order=asc"))
    assert set(asc[-2:]) == {"a/g", "c"}
    assert ids(await get(client, "?sort=added"))[0] == "c"  # newest first (c has age 0)
    assert ids(await get(client, "?sort=cost&order=desc"))[0] == "b"
    assert (await get(client, "?sort=set"))["total"] == 4
    assert (await get(client, "?sort=updated"))["total"] == 4
    assert (await client.get("/api/collection?sort=bogus")).status_code == 422


async def test_pagination_and_totals_cover_filtered_set(world, client):
    p1, p2 = await get(client, "?page_size=3&sort=name&order=asc"), await get(client, "?page_size=3&page=2&sort=name&order=asc")
    assert p1["total"] == p2["total"] == 4 and len(p1["items"]) == 3 and len(p2["items"]) == 1
    assert p1["totals"] == p2["totals"]                        # totals ignore paging
    assert (await get(client, "?page=9"))["items"] == []
    f = await get(client, "?graded=false")
    rows = [r for r in await coll.valuate(world) if not r["item"].get("grading")]
    exp = acquisition.cost_stats(rows)
    t = f["totals"]
    assert (t["stacks"], t["cards"]) == (3, 4)
    assert t["value"] == sum(r["value"] or 0 for r in rows)
    assert (t["cost"], t["pl"], t["cost_missing"]) == (exp["cost"], exp["pl"], exp["cost_missing"])


async def test_facets(world, client):
    f = (await client.get("/api/collection/facets")).json()
    assert {s["value"]: s["count"] for s in f["sets"]} == {"a": 2, "b": 1, "c": 1}
    assert {e["value"] for e in f["rarities"]} == {"Rare Holo", "Rare"}
    assert {e["value"]: e["count"] for e in f["languages"]} == {"en": 3, "ja": 1}
    assert f["graders"] == [{"value": "PSA", "count": 1}] and f["grades"] == [{"value": "9", "count": 1}]
    assert {e["value"] for e in f["types"]} == {"Fire", "Water"}


def test_grade_str():
    assert (cq.grade_str(9.0), cq.grade_str(9.5), cq.grade_str(10)) == ("9", "9.5", "10")


# ---- valuation cache ----

async def test_cache_reuses_until_bump(world, monkeypatch):
    monkeypatch.setattr(settings, "valuation_cache_ttl", 60)
    valuation_cache.bump()
    first = await coll.valuate(world)
    await world.collection_items.delete_many({})        # write that bypasses the hooks
    assert await coll.valuate(world) is first            # cached
    valuation_cache.bump()
    assert await coll.valuate(world) == []              # rebuilt after bump


async def test_cache_ttl_zero_disables(world):
    first = await coll.valuate(world)
    await world.collection_items.delete_many({})
    assert await coll.valuate(world) == [] and first


async def test_cache_not_shared_between_databases(world, monkeypatch):
    monkeypatch.setattr(settings, "valuation_cache_ttl", 60)
    valuation_cache.bump()
    assert len(await coll.valuate(world)) == 4
    other = world.client[world.name + "_other"]
    try:
        assert await coll.valuate(other) == []
    finally:
        await world.client.drop_database(other.name)


async def test_write_paths_invalidate(world, client, monkeypatch):
    monkeypatch.setattr(settings, "valuation_cache_ttl", 60)
    valuation_cache.bump()
    assert (await get(client))["totals"]["cost_missing"] == 1
    item = next(i for i in (await get(client))["items"] if i["cost"] is None)
    r = await client.patch(f"/api/collection/{item['id']}", json={"acquired": {"type": "purchased", "price": 50}})
    assert r.status_code == 200
    assert (await get(client))["totals"]["cost_missing"] == 0           # patch visible immediately
    await get(client)
    assert (await client.post(f"/api/collection/{item['id']}/remove", json={"quantity": 1})).status_code == 200
    assert (await get(client))["total"] == 3                            # remove visible immediately
    ids_ = [i["id"] for i in (await get(client))["items"]][:2]
    await get(client)
    assert (await client.post("/api/collection/bulk-acquired", json={"ids": ids_, "acquired": {"type": "gift"}})).status_code == 200
    assert (await get(client, "?acquisition=gift"))["total"] == 2       # bulk edit visible immediately
    p = await client.post("/api/collection", json={"card_id": "pokemon:a-1", "language": "en", "condition": "NM", "quantity": 1})
    assert p.status_code == 201
    assert (await get(client))["totals"]["cards"] >= 4                  # add visible immediately


async def test_price_write_invalidates(world, monkeypatch):
    monkeypatch.setattr(settings, "valuation_cache_ttl", 60)
    valuation_cache.bump()
    before = next(r for r in await coll.valuate(world) if r["item"]["card_id"] == "pokemon:c-3")
    assert before["value"] is None
    await store_card_prices(world, make_card("c", "3"), await get_rates(world))
    after = next(r for r in await coll.valuate(world) if r["item"]["card_id"] == "pokemon:c-3")
    assert after["value"] is not None


# ---- presets ----

async def test_presets_crud_and_validation(client):
    body = {"name": "Graded only", "scope": "collection", "query": {"graded": "true", "sort": "value"}}
    r = await client.post("/api/collection/presets", json=body)
    assert r.status_code == 201 and r.json()["query"] == body["query"]
    again = await client.post("/api/collection/presets", json={**body, "query": {"graded": "false"}})
    assert again.json()["id"] == r.json()["id"] and again.json()["query"] == {"graded": "false"}   # same name = overwrite
    await client.post("/api/collection/presets", json={"name": "Graded only", "scope": "wishlist", "query": {"filter": "hit"}})
    assert len((await client.get("/api/collection/presets")).json()) == 1                         # scopes are separate
    assert len((await client.get("/api/collection/presets?scope=wishlist")).json()) == 1
    assert (await client.post("/api/collection/presets", json={"name": "x", "query": {"$where": "1"}})).status_code == 422
    assert (await client.post("/api/collection/presets", json={"name": "  ", "query": {}})).status_code == 422
    assert (await client.post("/api/collection/presets", json={"name": "x", "query": {"q": "a" * 300}})).status_code == 422
    assert (await client.delete(f"/api/collection/presets/{r.json()['id']}")).status_code == 204
    assert (await client.delete(f"/api/collection/presets/{r.json()['id']}")).status_code == 404
    assert (await client.get("/api/collection/presets")).json() == []
