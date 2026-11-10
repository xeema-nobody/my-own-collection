from datetime import datetime, timezone

import httpx
import pytest

from app.main import app
from tests.conftest import make_card

CID = "pokemon:a-1"
L = {"platform": "vinted", "asking_price": 1500, "currency": "EUR", "listed_at": "2026-11-01"}


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


async def stack(db, qty=2, cost=500, key="k"):
    if not await db.cards.find_one({"_id": CID}):
        await db.cards.insert_one(make_card("a", "1"))
    acquired = {"type": "purchased", "price": cost, "currency": "EUR"} if cost is not None else None
    r = await db.collection_items.insert_one({
        "stack_key": key, "card_id": CID, "variant": None, "language": "en", "condition": "NM", "grading": None,
        "quantity": qty, "acquired": acquired, "created_at": datetime.now(timezone.utc)})
    return str(r.inserted_id)


async def test_listed_needs_a_listing_and_none_clears(db, client):
    sid = await stack(db)
    assert (await client.put(f"/api/collection/{sid}/sale", json={"status": "listed"})).status_code == 422
    r = await client.put(f"/api/collection/{sid}/sale", json={"status": "listed", "listings": [L]})
    sale = r.json()["sale"]
    assert sale["status"] == "listed" and sale["listings"][0]["asking_base"] == 1500
    r = await client.put(f"/api/collection/{sid}/sale", json={"status": "none", "listings": [L]})
    assert r.json()["sale"] == {"status": "none", "listings": []}
    assert "sale" not in await db.collection_items.find_one({})


async def test_bad_platform_url_and_unknown_stack(db, client):
    sid = await stack(db)
    bad = {**L, "platform": "tiktok"}
    assert (await client.put(f"/api/collection/{sid}/sale", json={"status": "listed", "listings": [bad]})).status_code == 422
    bad = {**L, "url": "javascript:alert(1)"}
    assert (await client.put(f"/api/collection/{sid}/sale", json={"status": "listed", "listings": [bad]})).status_code == 422
    assert (await client.put("/api/collection/" + "0" * 24 + "/sale", json={"status": "ready"})).status_code == 404


async def test_list_filter_totals_and_facets(db, client):
    a, b = await stack(db, key="a"), await stack(db, key="b")
    await client.put(f"/api/collection/{a}/sale", json={"status": "listed", "listings": [L]})
    await client.put(f"/api/collection/{b}/sale", json={"status": "ready"})
    out = (await client.get("/api/collection", params={"sale": "listed"})).json()
    assert out["total"] == 1 and out["totals"]["listed_value"] == 3000 and out["totals"]["listed_stacks"] == 1
    assert (await client.get("/api/collection", params={"sale": "active"})).json()["total"] == 2
    assert (await client.get("/api/collection", params={"sale": "none"})).json()["total"] == 0
    assert (await client.get("/api/collection", params={"platform": "vinted"})).json()["total"] == 1
    assert (await client.get("/api/collection", params={"platform": "ebay"})).json()["total"] == 0
    assert (await client.get("/api/collection", params={"sale": "bogus"})).status_code == 422
    assert (await client.get("/api/collection", params={"sort": "asking"})).json()["items"][0]["id"] == a
    f = (await client.get("/api/collection/facets")).json()
    assert {x["value"] for x in f["sale_statuses"]} == {"listed", "ready"} and f["platforms"][0]["value"] == "vinted"
    assert (await client.get("/api/collection/summary")).json()["listed_value"] == 3000


async def test_bulk_sale_drops_listings_and_reports(db, client):
    a = await stack(db, key="a")
    await client.put(f"/api/collection/{a}/sale", json={"status": "listed", "listings": [L]})
    r = (await client.post("/api/collection/bulk-sale", json={"ids": [a, "nope"], "status": "withdrawn"})).json()
    assert (r["updated"], r["failed"], r["results"][0]["dropped_listings"]) == (1, 1, 1)
    assert (await client.post("/api/collection/bulk-sale", json={"ids": [a], "status": "listed"})).status_code == 422


async def test_sold_realised_profit_and_partial_keeps_status(db, client):
    sid = await stack(db, qty=2, cost=500)
    await client.put(f"/api/collection/{sid}/sale", json={"status": "listed", "listings": [L, {**L, "platform": "ebay"}]})
    r = await client.post(f"/api/collection/{sid}/remove", json={
        "reason": "sold", "price": 1500, "platform": "vinted", "fees": 100, "shipping_paid": 50, "date": "2026-11-11"})
    assert r.json()["realised"] == 1500 - 100 - 50 - 500 and r.json()["delist"] == []  # copy left: still listed
    assert (await client.get("/api/collection", params={"sale": "listed"})).json()["total"] == 1
    ex = (await client.get("/api/collection/exits")).json()[0]
    assert (ex["platform"], ex["fees"], ex["realised"], ex["listed_days"]) == ("vinted", 100, 850, 10)
    r = await client.post(f"/api/collection/{sid}/remove", json={"reason": "sold", "price": 1500, "platform": "vinted"})
    assert r.json()["deleted"] is True and r.json()["delist"] == ["ebay"]  # other platform must be delisted


async def test_realised_is_none_not_zero_without_cost_or_price(db, client):
    nocost = await stack(db, qty=1, cost=None, key="a")
    r = await client.post(f"/api/collection/{nocost}/remove", json={"reason": "sold", "price": 900})
    assert r.json()["realised"] is None
    nop = await stack(db, qty=1, key="b")
    r = await client.post(f"/api/collection/{nop}/remove", json={"reason": "sold"})
    assert r.json()["realised"] is None
    gift = await stack(db, qty=1, key="c")
    r = await client.post(f"/api/collection/{gift}/remove", json={"reason": "gifted", "price": 900, "fees": 5})
    assert r.json()["realised"] is None
    ex = (await client.get("/api/collection/exits")).json()
    assert {e["fees"] for e in ex} == {None}


async def test_report(db, client):
    a, b = await stack(db, key="a"), await stack(db, key="b")
    await client.put(f"/api/collection/{a}/sale", json={"status": "listed", "listings": [L]})
    await client.put(f"/api/collection/{b}/sale", json={"status": "ready"})
    await client.post(f"/api/collection/{b}/remove", json={"reason": "sold", "price": 1000, "fees": 100, "quantity": 1})
    rep = (await client.get("/api/collection/sales/report")).json()
    assert rep["by_status"]["listed"] == {"stacks": 1, "cards": 2} and rep["listed_value"] == 3000
    assert rep["platforms"]["vinted"]["value"] == 3000
    assert rep["sold"]["sales"] == 1 and rep["sold"]["revenue"] == 1000 and rep["sold"]["realised"] == 400
    assert rep["sold"]["avg_days_to_sell"] is None


async def test_preset_accepts_sale_filters(client):
    r = await client.post("/api/collection/presets", json={"name": "L", "query": {"sale": "listed", "platform": "vinted"}})
    assert r.status_code == 201
