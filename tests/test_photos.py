import io
from datetime import datetime, timezone

import httpx
import pytest
from PIL import Image

from app.config import settings
from app.main import app
from app.services import collection as collection_svc
from tests.conftest import make_card

CID = "pokemon:a-1"


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


def jpeg(w=3000, h=2000, fmt="JPEG", exif_orientation=None, color=(200, 30, 30)):
    im = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    kw = {}
    if exif_orientation:
        ex = Image.Exif()
        ex[0x0112] = exif_orientation
        kw["exif"] = ex
    im.save(buf, fmt, **kw)
    return buf.getvalue()


async def stack(db, key="k"):
    if not await db.cards.find_one({"_id": CID}):
        await db.cards.insert_one(make_card("a", "1"))
    r = await db.collection_items.insert_one({
        "stack_key": key, "card_id": CID, "variant": None, "language": "en", "condition": "NM", "grading": None,
        "quantity": 1, "acquired": None, "created_at": datetime.now(timezone.utc)})
    return str(r.inserted_id)


async def test_upload_compresses_and_first_is_cover(db, client):
    sid = await stack(db)
    raw = jpeg()
    r = await client.post(f"/api/collection/{sid}/photos?kind=front", content=raw)
    assert r.status_code == 201
    p = r.json()
    assert p["cover"] is True and p["kind"] == "front" and max(p["w"], p["h"]) == settings.photo_max_side
    full = await client.get(f"/api/photos/{p['id']}")
    thumb = await client.get(f"/api/photos/{p['id']}?size=thumb")
    assert full.headers["content-type"] == "image/jpeg" and len(full.content) < len(raw)
    assert max(Image.open(io.BytesIO(thumb.content)).size) == settings.photo_thumb_side
    p2 = (await client.post(f"/api/collection/{sid}/photos?kind=back", content=jpeg(800, 600))).json()
    assert p2["cover"] is False and p2["order"] == 1 and (p2["w"], p2["h"]) == (800, 600)  # small stays small


async def test_exif_rotation_applied_and_stripped(db, client):
    sid = await stack(db)
    p = (await client.post(f"/api/collection/{sid}/photos", content=jpeg(400, 200, exif_orientation=6))).json()
    assert (p["w"], p["h"]) == (200, 400)
    out = Image.open(io.BytesIO((await client.get(f"/api/photos/{p['id']}")).content))
    assert not out.getexif()


async def test_rejects_junk_unknown_stack_bad_kind_and_limit(db, client, monkeypatch):
    sid = await stack(db)
    assert (await client.post(f"/api/collection/{sid}/photos", content=b"not an image")).status_code == 400
    assert (await client.post(f"/api/collection/{sid}/photos", content=b"")).status_code == 400
    assert (await client.post(f"/api/collection/{sid}/photos?kind=weird", content=jpeg(100, 100))).status_code == 422
    assert (await client.post("/api/collection/64b000000000000000000000/photos", content=jpeg(100, 100))).status_code == 404
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    assert (await client.post(f"/api/collection/{sid}/photos", content=gif.getvalue())).status_code == 400
    monkeypatch.setattr(settings, "photo_max_per_stack", 2)
    for _ in range(2):
        assert (await client.post(f"/api/collection/{sid}/photos", content=jpeg(100, 100))).status_code == 201
    assert (await client.post(f"/api/collection/{sid}/photos", content=jpeg(100, 100))).status_code == 409


async def test_cover_reorder_delete(db, client):
    sid = await stack(db)
    ids = [(await client.post(f"/api/collection/{sid}/photos", content=jpeg(100 + i, 100))).json()["id"] for i in range(3)]
    await client.patch(f"/api/photos/{ids[2]}", json={"cover": True})
    lst = (await client.get(f"/api/collection/{sid}/photos")).json()
    assert [p["id"] for p in lst if p["cover"]] == [ids[2]]
    await client.patch(f"/api/photos/{ids[2]}", json={"position": 0})
    assert [p["id"] for p in (await client.get(f"/api/collection/{sid}/photos")).json()] == [ids[2], ids[0], ids[1]]
    assert (await client.delete(f"/api/photos/{ids[2]}")).status_code == 204
    lst = (await client.get(f"/api/collection/{sid}/photos")).json()
    assert lst[0]["id"] == ids[0] and lst[0]["cover"] is True and len(lst) == 2
    assert (await client.get(f"/api/photos/{ids[2]}")).status_code == 404
    assert (await client.get("/api/photos/stats")).json()["count"] == 2


async def test_photos_go_with_the_stack_and_list_shows_count(db, client):
    sid = await stack(db)
    await client.post(f"/api/collection/{sid}/photos", content=jpeg(100, 100))
    page = (await client.get("/api/collection")).json()
    assert page["items"][0]["photo_count"] == 1 and page["items"][0]["cover_photo"]
    assert (await client.get("/api/collection?has_photos=true")).json()["total"] == 1
    assert (await client.get("/api/collection?has_photos=false")).json()["total"] == 0
    await collection_svc.remove(db, sid, quantity=1)
    assert await db.photos.count_documents({}) == 0


async def test_phone_route_only_for_just_scanned_stack(db, client):
    sid = await stack(db)
    r = await client.post(f"/api/scan/photo?stack_id={sid}", content=jpeg(100, 100))
    assert r.status_code == 403  # no scan event for this stack
    await db.scan_events.insert_one({"at": datetime.now(timezone.utc), "kind": "add", "stack_id": sid})
    r = await client.post(f"/api/scan/photo?stack_id={sid}&kind=front", content=jpeg(100, 100))
    assert r.status_code == 201
    await db.scan_events.update_many({}, {"$set": {"undone": True}})
    assert (await client.post(f"/api/scan/photo?stack_id={sid}", content=jpeg(100, 100))).status_code == 403


async def test_gate_allows_only_the_photo_post(db, monkeypatch):
    monkeypatch.setattr(settings, "lan_gate_secret", "s3cret")
    monkeypatch.setattr(settings, "lan_origin", "https://phone.example")
    h = {"x-moc-gate": "s3cret"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        assert (await c.post("/api/scan/photo?stack_id=x", content=b"x", headers=h)).status_code == 403  # route reached, scan check refuses
        r = await c.get("/api/photos/64b000000000000000000000", headers=h)
        assert r.status_code == 403 and "phone" in r.json()["detail"]
        assert (await c.post("/api/collection/64b000000000000000000000/photos", content=b"x", headers=h)).status_code == 403
        assert (await c.delete("/api/photos/64b000000000000000000000", headers=h)).status_code == 403
