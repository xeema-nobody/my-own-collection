from app.services.catalog_import import import_catalog, incomplete_sets, last_failed_sets
from app.services.refresh import refresh_prices
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


async def test_refresh_sets_touches_only_requested_sets(db):
    await import_catalog(None, catalog())
    prov = catalog()
    stats = await refresh_prices(sets=["b"], provider=prov)
    assert prov.calls == ["b"] and stats["scope"] == "sets" and stats["cards"] == 1  # not owned, still refreshed


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
