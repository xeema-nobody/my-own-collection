from app.services.catalog_import import import_catalog
from app.services.search import build_query, find_page
from app.services.sets import sets_with_stats
from conftest import FakeCatalog, make_card


def test_has_price_conditions():
    assert {"price_base": {"$ne": None}} in build_query(None, has_price=True)["$and"]
    assert {"price_base": None} in build_query(None, has_price=False)["$and"]
    assert build_query(None) == {}


async def seed(db):
    cards = [make_card("a", "1", priced=False), make_card("a", "2"), make_card("a", "3", priced=False),
             make_card("a", "4")]
    await import_catalog(None, FakeCatalog({"a": cards, "z": []}))
    await db.cards.update_one({"external_id": "a-2"}, {"$set": {"price_base": 500}})
    await db.cards.update_one({"external_id": "a-4"}, {"$set": {"price_base": 100}})


async def test_price_asc_nulls_last_and_paging_stable(db):
    await seed(db)
    p1 = await find_page(db, {}, "price_asc", 0, 2)
    p2 = await find_page(db, {}, "price_asc", 2, 2)
    assert [c["external_id"] for c in p1] == ["a-4", "a-2"]
    assert [c.get("price_base") for c in p2] == [None, None]
    assert {c["external_id"] for c in p1 + p2} == {"a-1", "a-2", "a-3", "a-4"}
    assert all("_s" not in c and "raw" not in c for c in p1 + p2)


async def test_sets_with_stats(db):
    await seed(db)
    by = {s["external_id"]: s for s in await sets_with_stats(db)}
    assert (by["a"]["cards_total"], by["a"]["cards_priced"]) == (4, 2)
    assert (by["z"]["cards_total"], by["z"]["cards_priced"]) == (0, 0)
