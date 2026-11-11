import io
import zipfile
from datetime import datetime, timezone

import httpx
import pytest
from PIL import Image

from app.main import app
from tests.conftest import make_card


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


def jpeg(color):
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), color).save(buf, "JPEG")
    return buf.getvalue()


async def stack(db, num="1", priced=True, qty=1, grading=None, condition="NM", language="en", key=None):
    cid = f"pokemon:a-{num}"
    if not await db.cards.find_one({"_id": cid}):
        await db.cards.insert_one(make_card("a", num, priced=priced))
        if priced:
            now = datetime.now(timezone.utc)
            await db.cards.update_one({"_id": cid}, {"$set": {
                "latest_price.cardmarket.market.raw._": {"market": 2000, "currency": "EUR", "as_of": now,
                                                          "observed_on": now.strftime("%Y-%m-%d")},
                "latest_price.tcgplayer.market.raw.holofoil": {"market": 1500, "currency": "EUR", "as_of": now,
                                                                "observed_on": now.strftime("%Y-%m-%d")}}})
    r = await db.collection_items.insert_one({
        "stack_key": key or f"k{num}{grading}", "card_id": cid, "variant": None, "language": language,
        "condition": None if grading else condition, "grading": grading, "quantity": qty, "acquired": None,
        "created_at": datetime.now(timezone.utc)})
    return str(r.inserted_id)


async def pack(client, ids, **kw):
    r = await client.post("/api/collection/listing-pack", json={"ids": ids, **kw})
    assert r.status_code == 200, r.text
    return r.json()


async def test_raw_text_and_price_strategies(db, client):
    sid = await stack(db, language="ja")
    market = (await pack(client, [sid]))["items"][0]
    assert market["price"] and "Near Mint" in market["description"] and "Japanese" in market["description"]
    assert market["title"].startswith("Charizard") and "Japanese" in market["title"]
    under = (await pack(client, [sid], strategy="under", pct=10))["items"][0]["price"]
    floor = (await pack(client, [sid], strategy="floor"))["items"][0]["price"]
    assert under == round(market["price"] * 0.9) or abs(under - market["price"] * 0.9) <= 1
    assert floor <= market["price"]


async def test_price_is_per_copy(db, client):
    one, three = await stack(db, "1", qty=1), await stack(db, "1", qty=3, key="x")
    a = (await pack(client, [one]))["items"][0]["price"]
    b = (await pack(client, [three]))["items"][0]["price"]
    assert abs(a - b) <= 1


async def test_no_price_is_none_with_warning_never_zero(db, client):
    sid = await stack(db, "2", priced=False)
    it = (await pack(client, [sid]))["items"][0]
    assert it["price"] is None and any("needs price" in w for w in it["warnings"])


async def test_slab_text_has_grade_and_cert(db, client):
    g = {"company": "PSA", "grade": 9, "cert_number": "123456", "report_url": "https://www.psacard.com/cert/123456"}
    sid = await stack(db, "3", grading=g)
    it = (await pack(client, [sid]))["items"][0]
    assert "PSA 9" in it["title"] and "cert 123456" in it["description"] and "psacard.com" in it["description"]


async def test_vinted_title_cut_with_warning_and_missing_reported(db, client):
    sid = await stack(db, "4")
    await db.cards.update_one({"_id": "pokemon:a-4"}, {"$set": {"name": "X" * 150}})
    r = await pack(client, [sid, "64b000000000000000000000"])
    assert len(r["items"][0]["title"]) <= 100 and any("title cut" in w for w in r["items"][0]["warnings"])
    assert r["missing"] == ["64b000000000000000000000"]


async def test_photos_cover_first_and_zip(db, client):
    sid = await stack(db, "5")
    p1 = (await client.post(f"/api/collection/{sid}/photos", content=jpeg((255, 0, 0)))).json()
    p2 = (await client.post(f"/api/collection/{sid}/photos", content=jpeg((0, 255, 0)))).json()
    await client.patch(f"/api/photos/{p2['id']}", json={"cover": True})
    it = (await pack(client, [sid]))["items"][0]
    assert it["photos"] == [p2["id"], p1["id"]] and "no photos" not in it["warnings"]
    z = await client.get(f"/api/collection/{sid}/photos.zip")
    assert z.headers["content-type"] == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(z.content)).namelist() == ["01.jpg", "02.jpg"]
    other = await stack(db, "6")
    assert (await client.get(f"/api/collection/{other}/photos.zip")).status_code == 404


async def test_cardmarket_sheet_skips_slabs_and_maps_condition(db, client):
    raw = await stack(db, "7", condition="LP", qty=2)
    slab = await stack(db, "8", grading={"company": "PSA", "grade": 10})
    pk = await pack(client, [raw, slab], platform="cardmarket")
    assert any("slab" in w for w in pk["items"][1]["warnings"])
    r = await client.get(f"/api/collection/listing-pack.csv?ids={raw},{slab}")
    lines = r.text.strip().splitlines()
    assert r.headers["content-type"].startswith("text/csv") and len(lines) == 2
    assert lines[0] == "name,set,number,language,condition,quantity,price,comment"
    assert ",EX,2," in lines[1]


async def test_mark_listed_uses_existing_sale_endpoint(db, client):
    sid = await stack(db, "9")
    price = (await pack(client, [sid]))["items"][0]["price"]
    r = await client.put(f"/api/collection/{sid}/sale", json={"status": "listed", "listings": [
        {"platform": "vinted", "asking_price": price, "listed_at": "2026-11-11"}]})
    assert r.json()["sale"]["status"] == "listed"


async def test_vinted_mapping_defaults_raw_vs_slab(db, client):
    raw = await stack(db, "5")
    slab = await stack(db, "6", grading={"company": "PSA", "grade": 9}, key="slab6")
    items = {i["item_id"]: i for i in (await pack(client, [raw, slab]))["items"]}
    assert (items[raw]["vinted_condition"], items[raw]["vinted_parcel"], items[raw]["slab"]) == ("Very good", "small", False)
    assert (items[slab]["vinted_condition"], items[slab]["vinted_parcel"], items[slab]["slab"]) == ("New without tags", "medium", True)
