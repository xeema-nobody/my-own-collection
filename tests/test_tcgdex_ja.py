"""Japanese TCGdex provider + import against canned responses (no network)."""
import json
from pathlib import Path

import httpx
import pytest

from app.providers.catalog import tcgdex
from app.providers.catalog.common import extract_prices
from app.providers.catalog.tcgdex import CatalogIndex, TcgdexJaCatalog, id_prefix, lang_base_url, map_card, map_set
from app.services.search import build_query

FIX = Path(__file__).parent / "fixtures/tcgdex_ja"
SET = json.loads((FIX / "set_SV2a.json").read_text())
MEW = json.loads((FIX / "card_SV2a-151.json").read_text())
BARE = json.loads((FIX / "card_SV2a-152_bare.json").read_text())
SETS = [{"id": "SV2a", "name": "ポケモンカード151"}, {"id": "BW3a", "name": "A"}, {"id": "BW3a", "name": "B"}]


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(tcgdex, "wait_random_exponential", lambda **kw: __import__("tenacity").wait_none())


def ja(index=None, wanted=None):
    en_calls = []

    def ja_handler(req):
        p = req.url.path
        return httpx.Response(200, json={"/sets": SETS, "/sets/SV2a": SET, "/cards/SV2a-151": MEW,
                                         "/cards/SV2a-152": BARE}.get(p)) if p in (
            "/sets", "/sets/SV2a", "/cards/SV2a-151", "/cards/SV2a-152") else httpx.Response(404)

    def en_handler(req):
        en_calls.append(str(req.url))
        dex = req.url.params["dexId"]
        return httpx.Response(200, json=[{"name": "Dark Mew"}, {"name": "Mew"}] if dex == "151" else [])

    c = TcgdexJaCatalog(index or CatalogIndex(), httpx.AsyncClient(base_url="http://up", transport=httpx.MockTransport(ja_handler)),
                        httpx.AsyncClient(base_url="http://en", transport=httpx.MockTransport(en_handler)), wanted)
    return c, en_calls


def test_ids_are_namespaced_and_english_unchanged():
    assert id_prefix("en") == "pokemon" and id_prefix("ja") == "pokemon-ja"
    assert lang_base_url("ja").endswith("/v2/ja")
    s = map_set(SET, "ja")
    assert s["_id"] == "pokemon-ja:SV2a" and s["language"] == "ja" and s["ptcgo_code"] == "SV2a" and s["printed_total"] == 165
    c = map_card(MEW, "SV2a", s, "ja", "Mew")
    assert c["_id"] == "pokemon-ja:SV2a-151" and c["language"] == "ja" and c["name_norm"] == "mew" and c["dex_id"] == 151
    assert "ミュウex" in c["search_text"] and "mew" in c["search_text"] and "151/165" in c["search_text"]
    assert c["images"]["small"] == "https://assets.tcgdex.net/ja/SV/SV2a/151/low.webp"
    assert extract_prices(c)[0]["currency"] == "EUR"


def test_bare_card_has_no_rarity_image_or_price():
    s = map_set(SET, "ja")
    c = map_card(BARE, "SV2a", s, "ja", None)
    assert c["rarity"] is None and c["images"] == {} and c["name_en"] is None and c["name_norm"] == ""
    assert extract_prices(c) == []   # missing price = nothing, never 0


async def test_available_sets_collapses_duplicate_ids():
    c, _ = ja()
    assert [s["id"] for s in await c.available_sets()] == ["SV2a", "BW3a"]


async def test_iter_cards_full_set_with_english_names_cached():
    c, en_calls = ja()
    cards = [x async for x in c.iter_cards("SV2a")]
    assert {x["_id"] for x in cards} == {"pokemon-ja:SV2a-151", "pokemon-ja:SV2a-152"}
    mew = next(x for x in cards if x["number"] == "151")
    assert mew["name_en"] == "Mew"                      # shortest English name of the dex id
    assert len(en_calls) == 1                           # the bare card has no dex id: no request


async def test_known_numbers_skipped_and_price_stub_for_only():
    c, _ = ja(CatalogIndex(numbers={"SV2a": {"151"}}))
    assert [x["number"] async for x in c.iter_cards("SV2a")] == ["152"]
    stub = [x async for x in c.iter_cards("SV2a", only={"pokemon-ja:SV2a-151"})]
    assert len(stub) == 1 and stub[0]["_prices_only"] and stub[0]["_id"] == "pokemon-ja:SV2a-151"


def test_search_native_text_and_mixed_case_code_and_language():
    assert build_query("ヤドキング") == {"$and": [{"search_text": {"$regex": "ヤドキング"}}]}
    q = build_query("SV2a-151", language="ja")["$and"]
    assert q[0]["external_id"]["$options"] == "i" and {"language": "ja"} in q


# ---- database-backed: import, refresh routing, scan / slab language guards ----
from app.services import catalog_ja, scan, slab  # noqa: E402
from app.providers.grading.base import CertInfo  # noqa: E402
from conftest import make_card  # noqa: E402


async def test_import_ja_sets_idempotent_and_never_touches_english(db):
    en = make_card("neo1", "1")                       # English neo1 shares its set code with a ja set
    await db.cards.insert_one(en)
    prov, _ = ja(wanted={"SV2a"})
    stats = await catalog_ja.import_ja_sets(["SV2a"], provider=prov)
    assert stats["cards"] == 2 and stats["failed_sets"] == [] and stats["language"] == "ja"
    assert await db.cards.count_documents({"language": "ja"}) == 2
    s = await db.sets.find_one({"_id": "pokemon-ja:SV2a"})
    assert s["imported_count"] == 2 and s["language"] == "ja" and s["complete"] is True   # fixture total 2
    prov2, _ = ja(await catalog_ja.ja_index(db), wanted={"SV2a"})
    again = await catalog_ja.import_ja_sets(["SV2a"], provider=prov2)
    assert again["cards"] == 0 and await db.cards.count_documents({"language": "ja"}) == 2   # re-run fetches nothing
    assert await db.cards.count_documents({"_id": en["_id"]}) == 1 and await db.collection_items.count_documents({}) == 0


async def test_list_ja_sets_reports_held_cards(db):
    prov, _ = ja()
    await db.sets.insert_one({"_id": "pokemon-ja:SV2a", "language": "ja", "external_id": "SV2a", "imported_count": 7})
    rows = {r["id"]: r for r in await catalog_ja.list_ja_sets(prov)}
    assert rows["SV2a"]["imported"] == 7 and rows["BW3a"]["imported"] == 0


async def _seed_ja(db):
    prov, _ = ja(wanted={"SV2a"})
    await catalog_ja.import_ja_sets(["SV2a"], provider=prov)
    await db.cards.insert_one(make_card("sv3pt5", "151"))


async def test_raw_scan_name_never_returns_ja_but_typed_set_code_does(db):
    await _seed_ja(db)
    scan.reset_names_cache()
    assert "mew" not in await scan.card_names(db)            # English scans are not diluted by ja names
    r = await scan.lookup(db, "151")                          # no set code: English only
    assert [c["id"] for c in r["cards"]] == ["pokemon:sv3pt5-151"]
    r = await scan.lookup(db, "151", "SV2a")                  # the code asks for the Japanese print
    assert [c["id"] for c in r["cards"]] == ["pokemon-ja:SV2a-151"]


async def test_search_finds_ja_by_english_and_native_name(db):
    await _seed_ja(db)
    for q in ("mew", "ミュウ"):
        assert (await scan.search(db, q))["total"] >= 1
    assert (await db.cards.count_documents(__import__("app.services.search", fromlist=["x"]).build_query("mew", language="ja"))) == 1


async def test_slab_japanese_page_matches_only_ja_prints(db):
    await _seed_ja(db)
    info = CertInfo(grader="PSA", cert="12345678", status="found", name="Mew ex", set_name="Pokemon Japanese 151",
                    number="151", language="Japanese", grade=10.0)
    slab.reset_sets_cache()
    cards = await slab.match_catalog(db, info)
    assert [c["id"] for c in cards] == ["pokemon-ja:SV2a-151"]
    en_info = CertInfo(grader="PSA", cert="12345679", status="found", name="Mew ex", set_name="Pokemon 151", number="151", grade=10.0)
    assert all(not c["id"].startswith("pokemon-ja") for c in await slab.match_catalog(db, en_info))
