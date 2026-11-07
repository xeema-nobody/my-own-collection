import json

import httpx
import pytest

from app.db.models import CollectionIn
from app.main import app
from app.services import acquisition as acq
from app.services import collection as coll
from app.services import portability as pf
from app.services import snapshots
from app.services.pricing import get_rates, store_card_prices
from tests.conftest import make_card

CID = "pokemon:a-1"


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


async def priced(db, *nums):
    for n in nums:
        doc = make_card("a", n)
        await db.cards.insert_one(doc)
        await store_card_prices(db, doc, await get_rates(db))


async def add(client, card="a-1", cond="NM", qty=1, acquired=None):
    body = {"card_id": f"pokemon:{card}", "condition": cond, "quantity": qty, "acquired": acquired}
    r = await client.post("/api/collection", json=body)
    assert r.status_code == 201
    return r.json()


# --- partial patch + log -------------------------------------------------------------------------

async def test_patch_merges_partial_fields_and_logs(db, client):
    await priced(db, "1")
    it = await add(client, acquired={"type": "purchased", "price": 500, "currency": "EUR", "source": "shop"})
    r = await client.patch(f"/api/collection/{it['id']}", json={"acquired": {"price": 700}})
    a = r.json()["acquired"]
    assert a["price"] == 700 and a["type"] == "purchased" and a["source"] == "shop"   # others kept
    h = (await client.get(f"/api/collection/{it['id']}/history")).json()
    assert len(h) == 1 and h[0]["before"]["price"] == 500 and h[0]["after"]["price"] == 700 and h[0]["action"] == "edit"


async def test_patch_null_clears_one_field_and_noop_not_logged(db, client):
    await priced(db, "1")
    it = await add(client, acquired={"type": "gift", "price": 0})
    await client.patch(f"/api/collection/{it['id']}", json={"acquired": {"price": None}})
    assert (await db.collection_items.find_one())["acquired"]["price"] is None
    await client.patch(f"/api/collection/{it['id']}", json={"acquired": {"price": None}})   # same again
    assert len(await db.collection_edits.find().to_list(None)) == 1
    assert (await client.patch(f"/api/collection/{it['id']}", json={"acquired": None})).status_code == 422
    assert (await client.patch(f"/api/collection/{it['id']}", json={"acquired": {"type": "stolen"}})).status_code == 422
    assert (await client.patch(f"/api/collection/{it['id']}", json={"acquired": {"currency": None}})).status_code == 422


async def test_patch_on_stack_without_acquired_and_unknown_id(db, client):
    await priced(db, "1")
    it = await add(client)
    r = await client.patch(f"/api/collection/{it['id']}", json={"acquired": {"type": "pulled", "price": 0}})
    assert r.json()["acquired"]["type"] == "pulled" and r.json()["acquired"]["currency"] == "EUR"
    assert (await client.patch("/api/collection/" + "0" * 24, json={"acquired": {"price": 1}})).status_code == 404
    assert (await client.patch(f"/api/collection/{it['id']}", json={"notes": "n"})).json()["notes"] == "n"


async def test_restore_brings_back_previous_value_and_is_logged(db, client):
    await priced(db, "1")
    it = await add(client, acquired={"type": "purchased", "price": 500})
    await client.patch(f"/api/collection/{it['id']}", json={"acquired": {"price": 9, "type": "gift"}})
    eid = (await client.get(f"/api/collection/{it['id']}/history")).json()[0]["id"]
    r = await client.post(f"/api/collection/{it['id']}/history/{eid}/restore")
    assert r.json()["acquired"]["price"] == 500 and r.json()["acquired"]["type"] == "purchased"
    h = (await client.get(f"/api/collection/{it['id']}/history")).json()
    assert [e["action"] for e in h] == ["restore", "edit"]
    assert (await client.post(f"/api/collection/{it['id']}/history/{'0' * 24}/restore")).status_code == 404


# --- bulk -----------------------------------------------------------------------------------------

async def test_bulk_applies_only_sent_fields(db, client):
    await priced(db, "1", "2")
    a = await add(client, "a-1", acquired={"type": "purchased", "price": 100, "source": "x"})
    b = await add(client, "a-2")
    r = await client.post("/api/collection/bulk-acquired",
                          json={"ids": [a["id"], b["id"], "0" * 24, "junk"], "acquired": {"type": "pulled", "price": 0}})
    assert r.json() == {"updated": 2, "unchanged": 0, "missing": ["0" * 24, "junk"]}
    docs = {d["card_id"]: d["acquired"] for d in await db.collection_items.find().to_list(None)}
    assert docs[CID]["type"] == "pulled" and docs[CID]["source"] == "x"
    again = await client.post("/api/collection/bulk-acquired", json={"ids": [a["id"]], "acquired": {"type": "pulled"}})
    assert again.json()["unchanged"] == 1
    assert (await db.collection_edits.count_documents({"action": "bulk"})) == 2


async def test_bulk_validation(db, client):
    assert (await client.post("/api/collection/bulk-acquired", json={"ids": ["x"], "acquired": {}})).status_code == 422
    assert (await client.post("/api/collection/bulk-acquired", json={"ids": [], "acquired": {"price": 1}})).status_code == 422


# --- merge on add --------------------------------------------------------------------------------

async def test_add_to_existing_stack_weights_the_price(db, client):
    await priced(db, "1")
    await add(client, qty=1, acquired={"type": "purchased", "price": 100})
    r = await add(client, qty=3, acquired={"type": "purchased", "price": 200})
    assert r["quantity"] == 4 and r["acquired"]["price"] == 175 and r["type_conflict"] is False
    assert (await db.collection_edits.find_one())["action"] == "merge"


async def test_add_type_conflict_keeps_old_type_and_flags(db, client):
    await priced(db, "1")
    await add(client, acquired={"type": "pulled", "price": 0})
    r = await add(client, acquired={"type": "purchased", "price": 300})
    assert r["acquired"]["type"] == "pulled" and r["type_conflict"] is True and r["acquired"]["price"] == 150


def test_weighted_merge_edge_cases():
    eur = {"price": 100, "currency": "EUR"}
    assert acq.weighted_merge(eur, None, 1, 1)[0] == acq.norm(eur)                # nothing new: unchanged
    assert acq.weighted_merge(None, eur, 1, 1)[0]["price"] == 100                  # nothing old: take new
    assert acq.weighted_merge({"currency": "EUR"}, eur, 2, 1)[0]["price"] == 100   # unknown old cost: take new
    out, conflict = acq.weighted_merge(eur, {"price": 5, "currency": "USD"}, 1, 1)
    assert out["price"] == 100 and conflict                                         # cannot average currencies


# --- P/L ------------------------------------------------------------------------------------------

async def test_summary_pl_ignores_unknown_cost_and_splits_pulled(db, client):
    await priced(db, "1", "2", "3")
    await add(client, "a-1", acquired={"type": "purchased", "price": 100})
    await add(client, "a-2", acquired={"type": "pulled", "price": 0})                # 0 = no cost, like blank
    await add(client, "a-3")                                                          # no cost at all
    rows = {r["card"]["_id"]: r for r in (await client.get("/api/collection")).json()["items"]}
    v1, v2, v3 = (rows[f"pokemon:a-{n}"]["value"] for n in (1, 2, 3))
    s = (await client.get("/api/collection/summary")).json()
    assert s["value"] == v1 + v2 + v3 and s["cost"] == 100
    assert s["pl"] == v1 - 100                         # stacks 2 (cost 0) and 3 (blank) excluded, never cost 0
    assert s["pl_ex_pulled"] == v1 - 100 and s["cost_ex_pulled"] == 100
    assert s["cost_missing"] == 2 and s["pulled_value"] == v2
    assert s["cost_basis_cost"] == 100 and s["cost_basis_cost_ex_pulled"] == 100 and s["cost_basis_value"] == v1
    assert s["by_type"]["pulled"] == {"stacks": 1, "cards": 1, "cost": 0, "value": v2}
    assert s["by_type"]["unset"]["stacks"] == 1


async def test_zero_and_blank_cost_are_no_cost_for_valuation(db, client):
    await priced(db, "1", "2", "3")
    await add(client, "a-1", acquired={"type": "purchased", "price": 0})
    await add(client, "a-2", acquired={"type": "purchased"})
    await add(client, "a-3", acquired={"type": "purchased", "price": 1})
    rows = {r["card"]["_id"]: r for r in (await client.get("/api/collection")).json()["items"]}
    assert rows["pokemon:a-1"]["cost"] is None and rows["pokemon:a-1"]["pl"] is None
    assert rows["pokemon:a-2"]["cost"] is None and rows["pokemon:a-2"]["pl"] is None
    assert rows["pokemon:a-3"]["cost"] > 0
    s = (await client.get("/api/collection/summary")).json()
    assert s["cost_missing"] == 2 and s["pl"] == rows["pokemon:a-3"]["value"] - rows["pokemon:a-3"]["cost"]


async def test_summary_pl_null_when_no_cost_known(db, client):
    await priced(db, "1")
    await add(client)
    s = (await client.get("/api/collection/summary")).json()
    assert s["pl"] is None and s["pl_ex_pulled"] is None and s["cost_missing"] == 1


async def test_snapshot_has_cost_fields(db):
    await priced(db, "1", "2")
    await coll.add(db, CollectionIn(card_id="pokemon:a-1", condition="NM", acquired={"type": "pulled", "price": 0}))
    await coll.add(db, CollectionIn(card_id="pokemon:a-2", condition="NM"))
    snap = await snapshots.take_snapshot(db)
    assert snap["total_cost"] == 0 and snap["total_cost_ex_pulled"] == 0 and snap["cost_missing_count"] == 2
    assert snap["pulled_value"] > 0 and snap["cost_basis_value"] == 0     # no stack has a cost above 0


# --- list filters --------------------------------------------------------------------------------

async def test_list_filters_by_type_and_missing_cost(db, client):
    await priced(db, "1", "2", "3")
    await add(client, "a-1", acquired={"type": "pulled", "price": 0})
    await add(client, "a-2", acquired={"type": "purchased", "price": 5})
    await add(client, "a-3")
    async def ids(q):
        return {i["card_id"] for i in (await client.get("/api/collection?" + q)).json()["items"]}
    assert await ids("acquisition=pulled") == {"pokemon:a-1"}
    assert await ids("acquisition=unset") == {"pokemon:a-3"}
    assert await ids("cost_missing=true") == {"pokemon:a-1", "pokemon:a-3"}      # cost 0 counts as missing
    assert await ids("cost_missing=false") == {"pokemon:a-2"}
    assert (await client.get("/api/collection?acquisition=bogus")).status_code == 422


# --- export / import -----------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["json", "csv"])
async def test_export_import_keeps_type(db, fmt):
    await priced(db, "1")
    await coll.add(db, CollectionIn(card_id=CID, condition="NM", acquired={"type": "gift", "price": 0}))
    items = await pf.export_items(db)
    raw = (pf.to_json(items) if fmt == "json" else await pf.to_csv(db, items)).encode()
    await db.collection_items.delete_many({})
    assert (await pf.import_items(db, pf.parse(raw, fmt)))["created"] == 1
    assert (await db.collection_items.find_one())["acquired"]["type"] == "gift"


async def test_old_export_without_type_imports_and_keeps_existing_type(db):
    await priced(db, "1")
    await coll.add(db, CollectionIn(card_id=CID, condition="NM", acquired={"type": "pulled", "price": 0}))
    old = json.dumps({"format": "moc-collection", "version": 1, "items": [
        {"card_id": CID, "language": "en", "condition": "NM", "quantity": 1,
         "acquired": {"price": 250, "currency": "EUR"}}]}).encode()
    res = await pf.import_items(db, pf.parse(old, "json"))
    assert res["updated"] == 1 and res["errors"] == []
    a = (await db.collection_items.find_one())["acquired"]
    assert a["type"] == "pulled" and a["price"] == 250                      # price restored, type not wiped
    e = await db.collection_edits.find_one({"action": "import"})
    assert e["before"]["price"] == 0 and e["after"]["price"] == 250


async def test_old_export_into_empty_db_has_no_type(db):
    await priced(db, "1")
    old = json.dumps({"format": "moc-collection", "version": 1, "items": [
        {"card_id": CID, "language": "en", "condition": "NM", "quantity": 1,
         "acquired": {"price": 250}}]}).encode()
    await pf.import_items(db, pf.parse(old, "json"))
    assert (await db.collection_items.find_one())["acquired"]["type"] is None
