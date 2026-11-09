"""Catalog coverage: printed set code lookups, set-field sync on import, the provider-vs-database audit."""
from app.services import scan
from app.services.catalog_audit import audit, classify
from app.services.catalog_import import import_catalog, sync_set_fields
from conftest import FakeCatalog, make_card


async def test_lookup_by_printed_set_code_when_card_lacks_it(db):
    """Cards imported before the provider sent the code carry none: the sets collection resolves it."""
    await db.cards.insert_one(make_card("sm11", "228"))
    await db.sets.insert_one({"_id": "pokemon:sm11", "tcg": "pokemon", "external_id": "sm11", "name": "Unified Minds",
                              "ptcgo_code": "UNM"})
    assert (await db.cards.find_one({}))["set"].get("ptcgo_code") is None
    r = await scan.lookup(db, "228", "UNM")
    assert [c["id"] for c in r["cards"]] == ["pokemon:sm11-228"]
    assert "UNM" .lower() in await scan.set_codes(db)


async def test_import_copies_set_code_onto_cards(db):
    await db.cards.insert_one(make_card("a", "1"))
    n = await sync_set_fields(db, [{"external_id": "a", "ptcgo_code": "AAA", "name": "Set A", "total": 12}])
    assert n == 1
    assert (await db.cards.find_one({}))["set"]["ptcgo_code"] == "AAA"
    assert await sync_set_fields(db, [{"external_id": "a", "ptcgo_code": "AAA", "name": "Set A", "total": 12}]) == 0  # idempotent
    # outside `only` only the code is copied, names / totals stay
    await sync_set_fields(db, [{"external_id": "a", "ptcgo_code": "BBB", "name": "Renamed", "total": 99}], only=["b"])
    got = (await db.cards.find_one({}))["set"]
    assert (got["ptcgo_code"], got["name"], got["total"]) == ("BBB", "Set A", 12)
    cat = FakeCatalog({"a": [make_card("a", "1")]})
    await import_catalog(["a"], cat)  # import path runs the sync without error


def test_classify_tags():
    p = {"total": 10, "ptcgo_code": "X"}
    assert classify(None, {"total": 10}, 3) == ["gone_upstream"]
    assert classify(p, None, 0) == ["new_at_provider"]
    assert classify(p, {"total": 10, "ptcgo_code": "X"}, 10) == []
    assert classify(p, {"total": 10, "ptcgo_code": "X"}, 0) == ["empty"]
    assert classify(p, {"total": 10, "ptcgo_code": "X"}, 7) == ["short"]
    assert classify(p, {"total": 10, "ptcgo_code": "X"}, 12) == ["over_total"]
    assert classify(p, {"total": 9, "ptcgo_code": "X"}, 10) == ["total_changed"]
    assert classify(p, {"total": 10}, 10) == ["code_missing"]


async def test_audit_reports_gaps(db):
    class Prov:
        async def list_sets(self):
            return [{"external_id": "a", "name": "A", "series": "S", "total": 2, "printed_total": 2},
                    {"external_id": "b", "name": "B Promos", "series": "S", "total": 5, "printed_total": 5},
                    {"external_id": "new", "name": "New", "series": "S", "total": 9, "printed_total": 9}]
    await db.sets.insert_many([{"_id": "pokemon:a", "tcg": "pokemon", "external_id": "a", "name": "A", "total": 2},
                               {"_id": "pokemon:b", "tcg": "pokemon", "external_id": "b", "name": "B Promos", "total": 5,
                                "printed_total": 5}])
    await db.cards.insert_many([make_card("a", "1"), make_card("a", "2"), make_card("b", "1")])
    out = await audit(db, Prov())
    assert out["provider_only"] == ["new"] and out["short"] == ["b"] and out["promo_sets"] == 1
    assert sorted(out["to_import"]) == ["b", "new"]
    assert {r["id"] for r in out["rows"]} == {"b", "new"}
