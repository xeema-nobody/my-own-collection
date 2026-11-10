"""TCGdex adapter against canned responses (real payload samples in tests/fixtures/tcgdex, no network)."""
import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.providers.catalog import tcgdex
from app.providers.catalog.common import extract_prices
from app.providers.catalog.pokemontcg import IncompletePage
from app.providers.catalog.tcgdex import CatalogIndex, TcgdexCatalog, card_number, match_sets

FIX = Path(__file__).parent / "fixtures/tcgdex"
SET = json.loads((FIX / "set_sv03.5.json").read_text())
MEW = json.loads((FIX / "card_sv03.5-205.json").read_text())
SETS = [{"id": "sv03.5", "name": "151", "cardCount": {"total": 207}},
        {"id": "swsh9", "name": "Brilliant Stars", "cardCount": {"total": 186}},
        {"id": "sv10.5b", "name": "Black Bolt", "cardCount": {"total": 172}},
        {"id": "A1", "name": "Genetic Apex", "cardCount": {"total": 286}, "serie": {"id": "tcgp"}},   # digital Pocket set
        {"id": "wp", "name": "W Promotional", "cardCount": {"total": 5}}]                            # declined by the user


def stub_card(local_id: str, **kw) -> dict:
    return {**MEW, "id": f"sv03.5-{local_id}", "localId": local_id, "name": f"Card {local_id}", **kw}


def provider(index, fail=(), cards=None):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        calls.append(path)
        if path == "/sets":
            return httpx.Response(200, json=SETS)
        if path == "/sets/sv03.5":
            return httpx.Response(200, json=SET)
        if path.startswith("/cards/"):
            cid = path.rsplit("/", 1)[-1]
            if cid in fail:
                return httpx.Response(500)
            return httpx.Response(200, json=(cards or {}).get(cid) or (MEW if cid == "sv03.5-205" else stub_card(cid.split("-")[1])))
        if path.startswith("/sets/"):  # sets we never imported: detail only (no cards needed)
            sid = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={**next(x for x in SETS if x["id"] == sid), "cards": [], "releaseDate": "2025-01-01"})
        return httpx.Response(404)
    return TcgdexCatalog(index, httpx.AsyncClient(base_url="http://up", transport=httpx.MockTransport(handler))), calls


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(tcgdex, "wait_random_exponential", lambda **kw: __import__("tenacity").wait_none())


def index(numbers=("1", "205")):
    return CatalogIndex(sets={"sv3pt5": {"name": "151", "total": 207}}, numbers={"sv3pt5": set(numbers)})


FULL = [str(i) for i in range(1, 208) if i != 2]  # every number but 2 known: 207 upstream, 206 here -> still room for 2
COMPLETE = [str(i) for i in range(1, 208)]          # as many cards as upstream: an unknown number is a numbering difference


def test_card_number_strips_padding_only():
    assert [card_number(x) for x in ("001", "205", "GG41", "TG05", "0")] == ["1", "205", "GG41", "TG05", "0"]


def test_match_sets_by_id_then_name_with_total_tiebreak():
    ours = {"swsh9": {"name": "Brilliant Stars", "total": 186}, "sv3pt5": {"name": "151", "total": 207},
            "zsv10pt5": {"name": "Black Bolt", "total": 172}, "fut20": {"name": "Futsal", "total": 5}}
    assert match_sets(ours, SETS) == {"swsh9": "swsh9", "sv3pt5": "sv03.5", "zsv10pt5": "sv10.5b"}
    dup = SETS + [{"id": "other", "name": "151", "cardCount": {"total": 10}}]
    assert match_sets({"sv3pt5": {"name": "151", "total": 207}}, dup) == {"sv3pt5": "sv03.5"}
    assert match_sets({"x": {"name": "151", "total": 5}}, dup) == {}  # ambiguous: no guess


async def test_list_sets_known_are_bare_new_are_full():
    p, _ = provider(index())
    sets = {s["external_id"]: s for s in await p.list_sets()}
    assert sets["sv3pt5"] == {"_id": "pokemon:sv3pt5", "tcg": "pokemon", "external_id": "sv3pt5"}  # upsert changes nothing
    assert "sv03.5" not in sets
    assert sets["swsh9"]["name"] == "Brilliant Stars" and sets["swsh9"]["total"] == 186 and sets["swsh9"]["release_date"].year == 2025


async def test_known_cards_refresh_prices_only_under_our_ids():
    p, calls = provider(index(COMPLETE))
    cards = [c async for c in p.iter_cards("sv3pt5", only={f"pokemon:sv3pt5-{n}" for n in COMPLETE})]
    assert [c["_id"] for c in cards] == ["pokemon:sv3pt5-1", "pokemon:sv3pt5-2", "pokemon:sv3pt5-205"]
    cards = cards[1:]  # 002 is known too, so also prices only
    cards = [cards[1]]
    mew = cards[0]
    assert mew["_prices_only"] and mew["_sources"] == ("cardmarket",)
    pts = extract_prices(mew)
    assert [(p_["source"], p_["currency"], p_["market"]) for p_ in pts] == [("cardmarket", "EUR", 2368)]
    assert pts[0]["avg30"] == 1779 and pts[0]["as_of"].year == 2026


async def test_unknown_cards_created_while_set_has_room_and_never_when_full():
    p, _ = provider(index(FULL))  # 206 of 207 known: number 2 is a card we miss
    cards = {c["_id"]: c async for c in p.iter_cards("sv3pt5")}
    new = cards["pokemon:sv3pt5-2"]
    assert not new.get("_prices_only") and new["set"]["id"] == "sv3pt5" and new["name"] == "Card 002"
    full, _ = provider(index(FULL + ["X1"]))  # as many cards as upstream, 2 not among them: numbering differs, skip
    assert "pokemon:sv3pt5-2" not in {c["_id"] async for c in full.iter_cards("sv3pt5")}


async def test_only_filters_requests_and_unmapped_set_yields_nothing():
    p, calls = provider(index(COMPLETE))
    cards = [c async for c in p.iter_cards("sv3pt5", only={"pokemon:sv3pt5-205"})]
    assert [c["_id"] for c in cards] == ["pokemon:sv3pt5-205"]
    assert calls.count("/cards/sv03.5-001") == 0
    assert [c async for c in p.iter_cards("nope")] == []


async def test_failed_card_is_reported_after_the_rest():
    p, _ = provider(index(COMPLETE), fail={"sv03.5-001"})
    got = []
    with pytest.raises(IncompletePage) as e:
        async for c in p.iter_cards("sv3pt5", only={f"pokemon:sv3pt5-{n}" for n in COMPLETE}):
            got.append(c["_id"])
    assert got == ["pokemon:sv3pt5-2", "pokemon:sv3pt5-205"] and e.value.missing == [(0, 1)]


def test_new_card_doc_matches_catalog_shape_and_gold_star():
    star = {**MEW, "id": "x-CC015", "localId": "CC015", "name": "Umbreon ☆", "category": "Pokemon", "hp": 70,
            "pricing": {"cardmarket": None, "tcgplayer": None}}
    doc = tcgdex.map_card(star, "cel25cc", {"name": "Celebrations Classic Collection", "total": 25})
    assert doc["_id"] == "pokemon:cel25cc-CC015" and doc["name"] == "Umbreon ★" and doc["supertype"] == "Pokémon"
    assert doc["name_norm"] and "umbreon" in doc["search_text"] and doc["hp"] == "70"
    assert doc["images"]["large"].endswith("/high.webp") and extract_prices(doc) == []


async def test_import_with_tcgdex_keeps_cards_and_tcgplayer_price(db):
    """Known cards keep their stored data; only Cardmarket is refreshed, TCGplayer survives."""
    from app.services.catalog_import import import_catalog
    from conftest import FakeCatalog, make_card

    from app.services.pricing import get_rates, store_card_prices
    await import_catalog(None, FakeCatalog({"sv3pt5": [make_card("sv3pt5", "205")]}))
    await store_card_prices(db, make_card("sv3pt5", "205"), await get_rates(db))   # import stores no prices now
    before = await db.cards.find_one({"_id": "pokemon:sv3pt5-205"})
    assert "tcgplayer" in before["latest_price"]
    p, _ = provider(index(COMPLETE))
    await db.collection_items.insert_one({"card_id": "pokemon:sv3pt5-205", "stack_key": "k", "quantity": 1})
    from app.services.refresh import refresh_prices
    await refresh_prices("tracked", provider=p)   # prices come from the tracked refresh, import is cards only
    after = await db.cards.find_one({"_id": "pokemon:sv3pt5-205"})
    assert after["name"] == before["name"] and after["rarity"] == before["rarity"]  # card doc untouched
    assert after["latest_price"]["tcgplayer"] == before["latest_price"]["tcgplayer"]
    assert after["latest_price"]["cardmarket"]["market"]["raw"]["_"]["market"] == 2368  # fresh from TCGdex (EUR 23.68)
    assert await db.cards.count_documents({}) == 1  # 001/002 of the fixture set were not created (set is complete)


async def test_get_catalog_picks_provider(monkeypatch, db):
    from app.config import settings
    from app.providers.catalog.pokemontcg import PokemonTcgCatalog
    from app.services.catalog_provider import get_catalog

    monkeypatch.delenv("CATALOG_PROVIDER", raising=False)   # a local .env may pin it
    assert Settings(_env_file=None).catalog_provider == "tcgdex"   # default after the 2026-11 flip
    monkeypatch.setattr(settings, "catalog_provider", "pokemontcg")
    assert isinstance(await get_catalog(), PokemonTcgCatalog)       # rollback path
    monkeypatch.setattr(settings, "catalog_provider", "tcgdex")
    assert isinstance(await get_catalog(), TcgdexCatalog)
    monkeypatch.setattr(settings, "catalog_provider", "nope")
    with pytest.raises(ValueError):
        await get_catalog()


async def test_set_numbered_differently_is_not_duplicated():
    odd = [str(i) + "_A" for i in range(1, 25)]  # like cel25c: '17_A' here, 'CC015' upstream
    p, _ = provider(index(odd))
    assert [c async for c in p.iter_cards("sv3pt5")] == []  # no number lines up: nothing matched, nothing created


async def test_extras_import_only_wanted_sets_and_missing_numbers(db):
    """Catalog extras: unwanted new sets are not stored, known numbers are not re-fetched, code comes from TCGdex."""
    from app.services.catalog_extras import ExtrasCatalog
    from app.services.catalog_import import import_catalog
    SETS.extend([{"id": "mep", "name": "MEP Black Star Promos", "cardCount": {"total": 2, "official": 0}},
                 {"id": "A1", "name": "Genetic Apex", "cardCount": {"total": 1, "official": 1}}])
    try:
        calls = []

        def handler(req):
            calls.append(req.url.path)
            if req.url.path == "/sets":
                return httpx.Response(200, json=SETS)
            if req.url.path == "/sets/mep":
                return httpx.Response(200, json={**SETS[-2], "abbreviation": {"official": "MEP"}, "releaseDate": "2025-09-26",
                                                 "cards": [{"id": "mep-060", "localId": "060"}, {"id": "mep-061", "localId": "061"}]})
            if req.url.path.startswith("/cards/mep-"):
                return httpx.Response(200, json=stub_card(req.url.path[-3:], id=req.url.path[-7:]))
            if req.url.path.startswith("/sets/"):
                sid = req.url.path.rsplit("/", 1)[-1]
                return httpx.Response(200, json={**next(x for x in SETS if x["id"] == sid), "cards": []})
            return httpx.Response(404)
        inner = TcgdexCatalog(index(COMPLETE), httpx.AsyncClient(base_url="http://up", transport=httpx.MockTransport(handler)))
        prov = ExtrasCatalog(inner, ["mep"])
        await import_catalog(["mep", "sv3pt5"], provider=prov)
        assert {s["external_id"] async for s in db.sets.find({})} >= {"mep"}
        assert not await db.sets.find_one({"external_id": "A1"})
        assert (await db.sets.find_one({"external_id": "mep"}))["ptcgo_code"] == "MEP"
        c = await db.cards.find_one({"_id": "pokemon:mep-61"})
        assert c and c["set"]["ptcgo_code"] == "MEP"
        assert not any(p.startswith("/cards/sv03.5") for p in calls)   # sv3pt5 complete: nothing fetched
    finally:
        del SETS[-2:]


async def test_import_mode_makes_no_request_for_known_cards():
    """An import (no `only`) stores nothing for known cards, so it must not fetch them (weekly cron: ~20k requests)."""
    p, calls = provider(index(COMPLETE))
    assert [c async for c in p.iter_cards("sv3pt5")] == []
    assert not [c for c in calls if c.startswith("/cards/")]
    room, calls = provider(index(FULL))   # number 2 missing: only that card is fetched
    assert [c["_id"] async for c in room.iter_cards("sv3pt5")] == ["pokemon:sv3pt5-2"]
    assert [c for c in calls if c.startswith("/cards/")] == ["/cards/sv03.5-002"]


async def test_list_sets_skips_pocket_and_declined_sets():
    p, _ = provider(index())
    ids = {s["external_id"] for s in await p.list_sets()}
    assert "A1" not in ids and "wp" not in ids and {"sv3pt5", "swsh9"} <= ids
