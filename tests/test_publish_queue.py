import io
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app.config import settings
from app.main import app
from tests.conftest import make_card


@pytest.fixture
async def client(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "publish_dir", str(tmp_path / "pub"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


def jpeg(color="red"):
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), color).save(buf, "JPEG")
    return buf.getvalue()


async def stack(db, client, n=1, photos=2, sale=None):
    cid = f"pokemon:a-{n}"
    if not await db.cards.find_one({"_id": cid}):
        await db.cards.insert_one(make_card("a", str(n)))
    r = await db.collection_items.insert_one({
        "stack_key": f"k{n}", "card_id": cid, "variant": None, "language": "en", "condition": "NM", "grading": None,
        "quantity": 1, "acquired": None, "created_at": datetime.now(timezone.utc), **({"sale": sale} if sale else {})})
    sid = str(r.inserted_id)
    for i in range(photos):
        assert (await client.post(f"/api/collection/{sid}/photos", content=jpeg(), headers={"content-type": "image/jpeg"})).status_code == 201
    return sid


def row(sid, **kw):
    return {"item_id": sid, "title": "Charizard - Base 4 - Near Mint", "description": "A card", "price": 1500,
            "condition": "Very good", "parcel": "small", **kw}


async def confirm(client, *rows):
    r = await client.post("/api/publish/confirm", json={"items": list(rows)})
    assert r.status_code == 201, r.text
    return r.json()


async def test_confirm_claim_publish_saves_listing(db, client):
    sid = await stack(db, client)
    out = await confirm(client, row(sid))
    assert out["queued"] == 1 and out["results"][0]["mode"] == "create"
    item = (await client.post("/api/publish/queue/next")).json()
    assert item["state"] == "publishing" and item["open_url"].endswith("/items/new")
    assert len(item["files"]) == 2 and item["files"][0].endswith("01.jpg")
    assert (Path(settings.publish_dir) / item["id"] / "01.jpg").exists()
    r = await client.post(f"/api/publish/queue/{item['id']}/result", json={"state": "published", "url": "https://www.vinted.nl/items/55-x"})
    assert r.status_code == 200 and r.json()["state"] == "published"
    assert not (Path(settings.publish_dir) / item["id"]).exists()  # temp photos removed
    st = (await db.collection_items.find_one({"stack_key": "k1"}))["sale"]
    assert st["status"] == "listed" and st["listings"][0]["url"].endswith("55-x") and st["listings"][0]["asking_price"] == 1500


async def test_one_at_a_time_and_empty_queue(db, client):
    a, b = await stack(db, client, 1), await stack(db, client, 2)
    assert (await client.post("/api/publish/queue/next")).json() is None
    await confirm(client, row(a), row(b))
    first = (await client.post("/api/publish/queue/next")).json()
    assert first["item_id"] == a
    assert (await client.post("/api/publish/queue/next")).status_code == 409  # first not reported yet
    await client.post(f"/api/publish/queue/{first['id']}/result", json={"state": "failed", "error": "captcha"})
    second = (await client.post("/api/publish/queue/next")).json()
    assert second["item_id"] == b


async def test_existing_link_means_update_and_keeps_other_platforms(db, client):
    sale = {"status": "listed", "listings": [
        {"platform": "vinted", "asking_price": 1000, "currency": "EUR", "url": "https://www.vinted.nl/items/777-old", "listed_at": "2026-11-01"},
        {"platform": "cardmarket", "asking_price": 1200, "currency": "EUR"}]}
    sid = await stack(db, client, sale=sale)
    assert (await confirm(client, row(sid, price=1400)))["results"][0]["mode"] == "update"
    item = (await client.post("/api/publish/queue/next")).json()
    assert item["open_url"] == "https://www.vinted.nl/items/777/edit"
    await client.post(f"/api/publish/queue/{item['id']}/result", json={"state": "published"})  # url falls back to the stored one
    ls = {l["platform"]: l for l in (await db.collection_items.find_one({"stack_key": "k1"}))["sale"]["listings"]}
    assert ls["vinted"]["asking_price"] == 1400 and ls["vinted"]["listed_at"] == "2026-11-01" and ls["cardmarket"]["asking_price"] == 1200


async def test_refuses_duplicates_no_photos_unknown_and_bad_input(db, client):
    sid, bare = await stack(db, client, 1), await stack(db, client, 2, photos=0)
    await confirm(client, row(sid))
    out = await confirm(client, row(sid), row(bare), row("0" * 24))
    assert [r["ok"] for r in out["results"]] == [False, False, False]
    assert "already" in out["results"][0]["error"] and "photos" in out["results"][1]["error"]
    for bad in (row(sid, price=0), row(sid, condition="Mint"), row(sid, title="")):
        assert (await client.post("/api/publish/confirm", json={"items": [bad]})).status_code == 422


async def test_release_cancel_retry(db, client):
    sid = await stack(db, client)
    await confirm(client, row(sid))
    item = (await client.post("/api/publish/queue/next")).json()
    assert (await client.post(f"/api/publish/queue/{item['id']}/release")).json()["state"] == "confirmed"
    assert not (Path(settings.publish_dir) / item["id"]).exists()
    again = (await client.post("/api/publish/queue/next")).json()
    await client.post(f"/api/publish/queue/{again['id']}/result", json={"state": "failed", "error": "dialog"})
    assert (await client.post(f"/api/publish/queue/{again['id']}/retry")).json()["state"] == "confirmed"
    assert (await client.post(f"/api/publish/queue/{again['id']}/cancel")).json()["state"] == "cancelled"
    assert (await client.post(f"/api/publish/queue/{again['id']}/cancel")).status_code == 409
    q = (await client.get("/api/publish/queue", params={"state": "cancelled"})).json()
    assert len(q) == 1 and q[0]["id"] == again["id"]
    assert (await client.get("/api/publish/queue", params={"state": "bogus"})).status_code == 422


def test_phone_gate_does_not_expose_publish():
    from app.security import PHONE_ALLOWED
    assert not any("publish" in path for _, path in PHONE_ALLOWED)
