from datetime import datetime, timezone

import httpx
import pytest

from app.main import app
from app.services.pricing import get_rates, store_card_prices
from tests.conftest import make_card

CID = "pokemon:a-1"


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


async def own(db, grade, key):
    await db.collection_items.insert_one({
        "stack_key": key, "card_id": CID, "variant": None, "language": "en", "quantity": 1,
        "condition": None if grade else "NM", "created_at": datetime.now(timezone.utc),
        "grading": {"company": "PSA", "grade": grade, "cert_number": None} if grade else None})


async def test_summary_and_filter_split_needs_price(db, client):
    doc = make_card("a", "1")
    await db.cards.insert_one(doc)
    await store_card_prices(db, doc, await get_rates(db))
    await own(db, None, "raw")
    await own(db, 9, "slab")
    s = (await client.get("/api/collection/summary")).json()
    assert (s["needs_price"], s["no_data"], s["unpriced"]) == (1, 0, 1)
    assert s["value"] == s["ref_raw_value"] > 0  # slab raw copy shown as info; the total counts the raw copy only
    rows = (await client.get("/api/collection?needs_price=true")).json()
    assert rows["total"] == 1 and rows["items"][0]["grading"]["grade"] == 9
    assert rows["items"][0]["value"] is None and rows["items"][0]["ref_raw_value"] == s["ref_raw_value"]
    assert (await client.get("/api/collection?needs_price=false")).json()["total"] == 1


async def test_fetch_without_any_target_is_422(db, client):
    r = await client.post("/api/admin/prices/fetch", json={})
    assert r.status_code == 422
