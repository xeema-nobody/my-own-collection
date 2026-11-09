from app.services.catalog_import import import_catalog, incomplete_sets, last_failed_sets
import pytest

from app.services.pricing import get_rates, store_card_prices, tracked_card_ids
from app.services.refresh import refresh_card_price, refresh_prices
from conftest import FakeCatalog, make_card


def catalog(**kw):
    return FakeCatalog({"a": [make_card("a", "1")], "b": [make_card("b", "1")], "c": [make_card("c", "1")]}, **kw)


async def test_retry_picks_only_failed_sets(db):
    flaky = catalog(fail={"b", "c"})
    stats = await import_catalog(None, flaky)
    assert stats["origin"] == "full" and stats["failed_sets"] == ["b", "c"]
    assert await last_failed_sets(db) == ["b", "c"]

    healthy = catalog()
    stats = await import_catalog(await last_failed_sets(db), healthy, retry=True)
    assert healthy.calls == ["b", "c"] and stats["failed_sets"] == [] and stats["origin"] == "retry"
    assert await db.cards.count_documents({}) == 3
    assert await last_failed_sets(db) == []  # retry run supersedes the failed full run


async def test_selected_import_does_not_hide_failures(db):
    await import_catalog(None, catalog(fail={"b"}))
    await import_catalog(["a"], catalog())  # unrelated single-set import afterwards
    assert await last_failed_sets(db) == ["b"]


async def track(db, card_id, wish=False):
    await (db.wishlist if wish else db.collection_items).insert_one({"card_id": card_id, "stack_key": card_id, "quantity": 1})


async def test_import_writes_no_price_rows(db):
    stats = await import_catalog(None, catalog())
    assert stats["cards"] == 3 and await db.prices.count_documents({}) == 0
    c = await db.cards.find_one({"_id": "pokemon:a-1"})
    assert c.get("price_base") is None and not c.get("latest_price")   # None, never 0


async def test_import_keeps_existing_prices(db):
    await import_catalog(None, catalog())
    await store_card_prices(db, make_card("a", "1"), await get_rates(db))
    await import_catalog(None, catalog())   # re-import must not wipe what was fetched
    assert (await db.cards.find_one({"_id": "pokemon:a-1"}))["price_base"] is not None


async def test_tracked_ids_are_collection_plus_wishlist(db):
    await track(db, "pokemon:a-1")
    await track(db, "pokemon:b-1", wish=True)
    assert await tracked_card_ids(db) == {"pokemon:a-1", "pokemon:b-1"}


async def test_refresh_touches_only_tracked_cards(db):
    await import_catalog(None, catalog())
    await track(db, "pokemon:a-1")
    await track(db, "pokemon:b-1", wish=True)
    prov = catalog()
    stats = await refresh_prices(provider=prov)
    assert prov.calls == ["a", "b"] and stats["cards"] == 2 and stats["scope"] == "tracked"
    priced = {c["_id"] async for c in db.cards.find({"price_base": {"$ne": None}})}
    assert priced == {"pokemon:a-1", "pokemon:b-1"}   # c-1 untracked: still None


async def test_refresh_scope_and_sets_narrow_tracked(db):
    await import_catalog(None, catalog())
    await track(db, "pokemon:a-1")
    await track(db, "pokemon:b-1", wish=True)
    prov = catalog()
    assert (await refresh_prices("wishlist", provider=prov))["cards"] == 1 and prov.calls == ["b"]
    prov = catalog()
    assert (await refresh_prices(sets=["a", "c"], provider=prov))["cards"] == 1 and prov.calls == ["a"]
    with pytest.raises(ValueError):
        await refresh_prices("all", provider=catalog())


async def test_new_tracked_card_gets_one_price_fetch(db):
    await import_catalog(None, catalog())
    prov = catalog()
    out = await refresh_card_price(db, "pokemon:c-1", prov)   # untracked, user pressed "Fetch price"
    assert out == {"found": True, "prices": out["prices"], "tracked": False} and out["prices"] > 0
    assert prov.calls == ["c"] and (await db.cards.find_one({"_id": "pokemon:c-1"}))["price_base"] is not None
    assert (await db.cards.find_one({"_id": "pokemon:a-1"})).get("price_base") is None
    with pytest.raises(LookupError):
        await refresh_card_price(db, "pokemon:nope-1", prov)


async def test_short_set_is_flagged_then_completed(db):
    short = FakeCatalog({"a": [make_card("a", "1")]}, totals={"a": 3})
    stats = await import_catalog(None, short)
    s = await db.sets.find_one({"_id": "pokemon:a"})
    assert (s["imported_count"], s["complete"]) == (1, False)
    assert stats["failed_sets"] == ["a"] and stats["incomplete_sets"] == ["a"]
    assert (await db.jobs.find_one({"type": "catalog_import"}))["status"] == "partial"
    assert await incomplete_sets(db) == ["a"]

    full = FakeCatalog({"a": [make_card("a", str(n)) for n in (1, 2, 3)]}, totals={"a": 3})
    stats = await import_catalog(await incomplete_sets(db), full, retry=True)
    s = await db.sets.find_one({"_id": "pokemon:a"})
    assert (s["imported_count"], s["complete"]) == (3, True) and stats["failed_sets"] == []
    assert await incomplete_sets(db) == []


async def test_unknown_total_counts_as_complete(db):
    stats = await import_catalog(None, catalog())
    assert stats["failed_sets"] == [] and (await db.sets.find_one({"_id": "pokemon:a"}))["complete"] is True
