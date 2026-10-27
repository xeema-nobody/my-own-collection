from app.services.catalog_import import import_catalog, last_failed_sets
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
