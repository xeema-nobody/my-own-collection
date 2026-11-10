"""'Import this Japanese set' prompt: suggestions, the import endpoint, progress, phone gate. No network."""
import json
from pathlib import Path

import httpx
import pytest

from app.main import app
from app.providers.catalog.tcgdex import TcgdexJaCatalog
from app.services import catalog_ja, ja_suggest

SETS = json.loads((Path(__file__).parent / "fixtures/tcgdex_ja/sets_list.json").read_text())


def client(headers=None):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost", headers=headers or {})


@pytest.fixture(autouse=True)
def ja_list(monkeypatch, db):
    async def fake_list(provider=None):
        held = {s["external_id"]: s.get("imported_count", 0) async for s in db.sets.find({"language": "ja"}, {"external_id": 1, "imported_count": 1})}
        return [{"id": s["id"], "name": s["name"], "total": s["cardCount"]["total"], "printed_total": s["cardCount"]["official"],
                 "imported": held.get(s["id"], 0)} for s in SETS]
    monkeypatch.setattr(catalog_ja, "list_ja_sets", fake_list)
    ja_suggest.reset_cache()
    yield
    ja_suggest.reset_cache()


async def ids(**kw):
    return [s["id"] for s in await ja_suggest.suggest(**kw)]


async def test_set_code_is_the_strongest_signal_case_insensitive():
    got = await ja_suggest.suggest(code="s9", total=100)
    assert got[0]["id"] == "S9" and "set code" in got[0]["reason"] and "printed total" in got[0]["reason"]


async def test_english_set_name_uses_aliases():
    assert await ids(set_name="2022 STAR BIRTH") == ["S9"]
    assert await ids(set_name="2000 P.M. JAPANESE NEO") == ["neo1", "neo2", "neo3", "neo4"]


async def test_total_alone_is_not_a_signal_and_no_signal_gives_nothing():
    assert await ids(total=100) == []
    assert await ids() == []


async def test_search_matches_id_and_kana_name():
    assert await ids(q="151") == ["SV2a"] and await ids(q="sv2") == ["SV2a"] and await ids(q="スター") == ["S9"]


async def test_suggest_endpoint_degrades_to_empty_when_upstream_is_down(monkeypatch):
    async def boom(provider=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(catalog_ja, "list_ja_sets", boom)
    async with client() as c:
        r = await c.get("/api/scan/ja/suggest", params={"code": "S9"})
    assert r.status_code == 200 and r.json() == {"sets": []}


async def test_import_rejects_unknown_set_and_starts_one_known_set(monkeypatch, db):
    started = []

    async def fake_import(set_ids, provider=None, trigger="manual"):
        started.append((set_ids, trigger))
    monkeypatch.setattr(catalog_ja, "import_ja_sets", fake_import)
    async with client() as c:
        assert (await c.post("/api/scan/ja/import", params={"set": "NOPE"})).status_code == 404
        r = await c.post("/api/scan/ja/import", params={"set": "S9"})
    assert r.status_code == 202 and r.json() == {"started": True, "set": "S9"}
    import asyncio
    await asyncio.sleep(0)
    assert started == [(["S9"], "scan")]


async def test_import_busy_is_409(db):
    await db.jobs.insert_one({"type": "catalog_import", "status": "running", "stats": {}})
    async with client() as c:
        assert (await c.post("/api/scan/ja/import", params={"set": "S9"})).status_code == 409


async def test_import_writes_catalog_only_never_the_collection(db):
    """The real job (fake upstream provider) adds ja sets/cards and leaves the collection alone."""
    card = {"_id": "pokemon-ja:S9-103", "tcg": "pokemon", "language": "ja", "number": "103", "name": "リザードンV",
            "set": {"id": "S9"}}

    class P(TcgdexJaCatalog):
        def __init__(self): pass
        async def list_sets(self):
            return [{"_id": "pokemon-ja:S9", "tcg": "pokemon", "language": "ja", "external_id": "S9", "name": "x", "total": 1}]
        async def iter_cards(self, set_id=None, only=None):
            yield card
    out = await catalog_ja.import_ja_sets(["S9"], provider=P(), trigger="scan")
    assert out["cards"] == 1 and out["language"] == "ja"
    assert await db.cards.count_documents({"language": "ja"}) == 1
    assert await db.collection.count_documents({}) == 0 and await db.wishlist.count_documents({}) == 0
    job = await db.jobs.find_one({"type": "catalog_import"})
    assert job["trigger"] == "scan" and job["stats"]["language"] == "ja"


async def test_status_idle_running_and_done(db):
    async with client() as c:
        assert (await c.get("/api/scan/ja/import")).json()["state"] == "idle"
        await db.sets.insert_one({"_id": "pokemon-ja:S9", "total": 127})
        await db.cards.insert_many([{"_id": f"pokemon-ja:S9-{i}", "tcg": "pokemon", "language": "ja", "set": {"id": "S9"}} for i in range(3)])
        jid = (await db.jobs.insert_one({"type": "catalog_import", "status": "running", "started_at": __import__("datetime").datetime.now(),
                                         "stats": {"language": "ja", "set_ids": ["S9"]}})).inserted_id
        r = (await c.get("/api/scan/ja/import")).json()
        assert r == {"state": "running", "set": "S9", "done": 3, "expected": 127, "failed": []}
        await db.jobs.update_one({"_id": jid}, {"$set": {"status": "ok"}})
        assert (await c.get("/api/scan/ja/import")).json()["state"] == "done"


async def test_other_language_job_is_not_reported(db):
    await db.jobs.insert_one({"type": "catalog_import", "status": "running", "started_at": __import__("datetime").datetime.now(),
                              "stats": {"set_ids": ["base1"]}})
    async with client() as c:
        assert (await c.get("/api/scan/ja/import")).json()["state"] == "idle"


async def test_phone_gate_allows_the_three_routes_and_nothing_else_in_admin(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "lan_gate_secret", "s3cret")
    monkeypatch.setattr(settings, "lan_origin", "https://localhost")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                                 headers={"x-moc-gate": "s3cret"}) as c:
        assert (await c.get("/api/scan/ja/suggest", params={"code": "S9"})).status_code == 200
        assert (await c.get("/api/scan/ja/import")).status_code in (200, 500)
        assert (await c.post("/api/admin/catalog/ja/import", params={"sets": "S9"})).status_code == 403
        assert (await c.get("/api/admin/catalog/ja/sets")).status_code == 403
