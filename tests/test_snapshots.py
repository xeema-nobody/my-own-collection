import httpx

from app.main import app
from app.services.snapshots import take_snapshot


async def test_snapshot_rerun_same_day_replaces_not_duplicates(db):
    await take_snapshot(db)
    await db.collection_items.insert_one({"stack_key": "k", "card_id": "pokemon:missing", "quantity": 2,
                                          "language": "en", "condition": "NM", "grading": None, "variant": None})
    again = await take_snapshot(db)
    assert await db.collection_snapshots.count_documents({}) == 1
    assert again["item_count"] == 1  # second run overwrote the first (empty) one


async def test_history_hides_legacy_snapshots(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        await _history_checks(db, client)


async def _history_checks(db, client):
    await db.collection_snapshots.insert_many([
        {"date": "2026-10-20", "total_value": 95586},                           # raw-fallback era, no version
        {"date": "2026-10-29", "total_value": 40000, "valuation_version": 2}])
    r = await client.get("/api/dashboard/history?days=3650")
    assert [s["date"] for s in r.json()] == ["2026-10-29"] and r.json()[0]["legacy_valuation"] is False
    r = await client.get("/api/dashboard/history?days=3650&include_legacy=true")
    assert [(s["date"], s["legacy_valuation"]) for s in r.json()] == [("2026-10-20", True), ("2026-10-29", False)]
