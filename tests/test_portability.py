import httpx
import pytest

from app.db.models import CollectionIn
from app.main import app
from app.services import collection as coll
from app.services import portability as pf
from tests.conftest import make_card


async def seed(db):
    await db.cards.insert_many([make_card("a", "1"), make_card("a", "2")])
    await coll.add(db, CollectionIn(card_id="pokemon:a-1", condition="NM", quantity=2,
                                    acquired={"price": 1250, "currency": "EUR", "date": "2026-01-02",
                                              "source": "cardmarket"},
                                    notes="first, \"quoted\"", tags=["trade", "binder 1"]))
    await coll.add(db, CollectionIn(card_id="pokemon:a-1", condition="LP", language="ja"))
    await coll.add(db, CollectionIn(card_id="pokemon:a-2", variant="holofoil",
                                    grading={"company": "PSA", "grade": 9.5, "cert_number": "123"}))


async def snapshot(db):
    return {d["stack_key"]: {k: v for k, v in d.items() if k not in ("_id", "updated_at")}
            async for d in db.collection_items.find()}


@pytest.mark.parametrize("fmt", ["json", "csv"])
async def test_round_trip(db, fmt):
    await seed(db)
    before = await snapshot(db)
    items = await pf.export_items(db)
    raw = (pf.to_json(items) if fmt == "json" else await pf.to_csv(db, items)).encode()
    await db.collection_items.delete_many({})
    res = await pf.import_items(db, pf.parse(raw, fmt))
    assert res == {"created": 3, "updated": 0, "errors": []}
    after = await snapshot(db)
    if fmt == "csv":  # CSV carries no created_at
        for d in (*before.values(), *after.values()):
            d.pop("created_at")
    assert after == before


async def test_export_has_no_internal_fields(db):
    await seed(db)
    for i in await pf.export_items(db):
        assert not {"_id", "id", "stack_key"} & i.keys()


async def test_import_idempotent_and_add_mode(db):
    await seed(db)
    raw = pf.to_json(await pf.export_items(db)).encode()
    first = await snapshot(db)
    res = await pf.import_items(db, pf.parse(raw, "json"))
    assert (res["created"], res["updated"]) == (0, 3)
    assert await snapshot(db) == first
    await pf.import_items(db, pf.parse(raw, "json"), mode="add")
    assert sorted(d["quantity"] for d in (await snapshot(db)).values()) == [2, 2, 4]


async def test_set_mode_restores_edited_fields(db):
    await seed(db)
    raw = pf.to_json(await pf.export_items(db)).encode()
    await db.collection_items.update_many({}, {"$set": {"notes": "changed", "tags": [], "quantity": 9}})
    await pf.import_items(db, pf.parse(raw, "json"))
    d = await db.collection_items.find_one({"card_id": "pokemon:a-1", "condition": "NM"})
    assert (d["notes"], d["tags"], d["quantity"]) == ('first, "quoted"', ["trade", "binder 1"], 2)


async def test_bad_rows_reported_good_rows_applied(db):
    await seed(db)
    await db.collection_items.delete_many({})
    rows = [{"card_id": "pokemon:a-1", "condition": "NM"},
            {"card_id": "pokemon:nope", "condition": "NM"},
            {"card_id": "pokemon:a-1", "condition": "NM", "grading": {"company": "PSA", "grade": 9}},
            {"card_id": "pokemon:a-1", "condition": "NM", "language": "xx"},
            "junk"]
    res = await pf.import_items(db, rows)
    assert (res["created"], [e["row"] for e in res["errors"]]) == (1, [2, 3, 4, 5])
    assert "card not found" in res["errors"][0]["error"]
    assert await db.collection_items.count_documents({}) == 1


@pytest.mark.parametrize("raw,fmt", [(b"\xff\xfe", "json"), (b"{nope", "json"), (b"[]", "json"),
                                     (b'{"format":"moc-collection","version":9,"items":[]}', "json")])
def test_parse_rejects_malformed(raw, fmt):
    with pytest.raises(ValueError):
        pf.parse(raw, fmt)


async def test_api_export_import(db):
    await seed(db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        r = await c.get("/api/collection/export", params={"format": "csv"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]
        assert r.text.splitlines()[0].startswith("card_id,name,set,number")
        j = await c.get("/api/collection/export")
        assert j.json()["format"] == "moc-collection" and len(j.json()["items"]) == 3
        up = await c.post("/api/collection/import", params={"format": "json"}, content=j.content)
        assert up.json() == {"created": 0, "updated": 3, "errors": []}
        bad = await c.post("/api/collection/import", content=b"{nope")
        assert bad.status_code == 400
        assert (await c.get("/api/collection/export", params={"format": "xml"})).status_code == 422


async def test_import_bad_field_types_are_row_errors(db):
    await seed(db)
    rows = [{"card_id": ["x"], "condition": "NM"},
            {"card_id": "pokemon:a-1", "condition": "NM", "created_at": 5},
            {"card_id": "pokemon:a-2", "condition": "NM", "created_at": "not a date"}]
    res = await pf.import_items(db, rows)
    assert res["created"] == 0 and [e["row"] for e in res["errors"]] == [1, 2, 3]


async def test_import_endpoint_streams_with_cap(db, monkeypatch):
    from app.api import collection as api
    monkeypatch.setattr(api, "MAX_UPLOAD", 100)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        r = await c.post("/api/collection/import", content=b"x" * 101)
        assert r.status_code == 413
        r = await c.post("/api/collection/import", content=b"x" * 101,
                         headers={"content-length": "5"})   # lying header: the stream cap still applies
        assert r.status_code in (413, 400)
