"""services/slab.py: cert cache, catalog match, exactness per grader, enrich on add, API + gate. No live network."""
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.main import app
from app.providers.grading.base import FOUND, CertInfo, now
from app.services import slab
from tests.test_scan import card

FX = Path(__file__).parent / "fixtures" / "cert"


def ace(name):
    return httpx.MockTransport(lambda req: httpx.Response(200, text=(FX / name).read_text()))


@pytest.fixture
async def cat(db):
    slab.reset_sets_cache()
    go = lambda num, name="Radiant Charizard": card("pgo", num, name)  # noqa: E731
    await db.cards.insert_many([go("11"), card("base1", "4"), card("sv3pt5", "6", "Charizard ex"),
                                card("xy1", "142", "Blastoise-EX"), card("other", "11", "Radiant Charizard")])
    await db.cards.update_one({"_id": "pokemon:pgo-11"}, {"$set": {"set.name": "Pokemon GO", "set.printed_total": 78,
                                                                    "set.release_date": now().replace(year=2022)}})
    await db.cards.update_one({"_id": "pokemon:xy1-142"}, {"$set": {"set.printed_total": 146}})
    return db


def info(grader="ACE", **kw):
    base = dict(grader=grader, cert="1", status=FOUND, url="https://x/1", fetched_at=now())
    return CertInfo(**{**base, **kw})


async def test_ace_exact_when_name_number_total_agree_on_one_print(cat):
    got = await slab.lookup(cat, "ACE", "158690", transport=ace("ace_158690.html"))
    top = got["cards"][0]
    assert top["id"] == "pokemon:pgo-11" and top["signals"][:3] == ["name", "number", "total"]
    assert {"set", "year"} <= set(top["signals"])
    assert (got["how_exact"], got["needs_confirm"], got["cached"]) == ("exact", False, False)
    assert got["report_url"] == "https://acegrading.com/cert/158690"
    assert got["cert"]["grade"] == 10.0 and top["variant_hint"] == "holofoil"


async def test_psa_and_bgs_never_exact(cat):
    for grader in ("PSA", "BGS"):
        i = info(grader, name="BLASTOISE-EX", number="142", printed_total=146)
        cards = await slab.match_catalog(cat, i)
        assert cards[0]["id"] == "pokemon:xy1-142"
        assert slab.how_exact(grader, cards) == "likely"


async def test_psa_without_total_and_bgs_without_number_are_likely_or_possible(cat):
    psa = await slab.match_catalog(cat, info("PSA", name="Charizard", number="4"))
    assert psa[0]["id"] == "pokemon:base1-4" and slab.how_exact("PSA", psa) == "likely"
    bgs = await slab.match_catalog(cat, info("BGS", name="Radiant Charizard", set_name="Pokemon GO", year=2022))
    assert bgs[0]["id"] == "pokemon:pgo-11" and slab.how_exact("BGS", bgs) == "likely"
    two = await slab.match_catalog(cat, info("BGS", name="Radiant Charizard"))  # two prints, nothing separates them
    assert slab.how_exact("BGS", two) == "possible"


async def test_not_in_catalog_gives_no_cards(cat):
    i = info(name="Totally Unknown Mon", number="9", printed_total=9)
    assert await slab.match_catalog(cat, i) == [] and slab.how_exact("ACE", []) == "none"


async def test_japanese_number_only_fallback_when_name_unknown(cat):
    cards = await slab.match_catalog(cat, info(name="リザードン", number="142/146", printed_total=146))
    assert [c["id"] for c in cards] == ["pokemon:xy1-142"] and "name" not in cards[0]["signals"]


async def test_cache_hit_avoids_second_request_and_counts(cat):
    calls = []
    def handler(req):
        calls.append(1)
        return httpx.Response(200, text=(FX / "ace_158690.html").read_text())
    t = httpx.MockTransport(handler)
    a = await slab.lookup(cat, "ace", "158690", transport=t)
    b = await slab.lookup(cat, "ACE", "#158690", transport=t)
    assert (a["cached"], b["cached"], len(calls)) == (False, True, 1)
    assert (await cat.cert_cache.find_one({"_id": "ACE:158690"}))["lookups"] == 2
    await slab.lookup(cat, "ACE", "158690", transport=t, refresh=True)
    assert len(calls) == 2


async def test_not_found_is_cached_short_and_expires(cat):
    calls = []
    t = httpx.MockTransport(lambda r: (calls.append(1), httpx.Response(200, text=(FX / "ace_notfound.html").read_text()))[1])
    got = await slab.lookup(cat, "ACE", "999999", transport=t)
    assert got["cert"]["status"] == "not_found" and got["cards"] == [] and got["how_exact"] == "none"
    doc = await cat.cert_cache.find_one({"_id": "ACE:999999"})
    assert doc["expires_at"] - now() <= timedelta(hours=1, minutes=1)
    await cat.cert_cache.update_one({"_id": "ACE:999999"}, {"$set": {"expires_at": now() - timedelta(seconds=1)}})
    await slab.lookup(cat, "ACE", "999999", transport=t)
    assert len(calls) == 2


async def test_unavailable_and_invalid_are_not_cached(cat):
    def boom(req):
        raise httpx.ConnectTimeout("t")
    got = await slab.lookup(cat, "ACE", "158690", transport=httpx.MockTransport(boom))
    assert got["cert"]["status"] == "unavailable" and got["report_url"].endswith("/158690")
    bad = await slab.lookup(cat, "ACE", "../x")
    assert bad["cert"]["status"] == "invalid" and bad["report_url"] is None
    assert await cat.cert_cache.count_documents({}) == 0


async def test_link_only_grader_is_recorded_and_countable(cat):
    got = await slab.lookup(cat, "CGC", "1234567")
    assert got["cert"]["status"] == "link_only" and got["report_url"] == "https://www.cgccards.com/certlookup/1234567/"
    await slab.lookup(cat, "CGC", "1234567")
    doc = await cat.cert_cache.find_one({"_id": "CGC:1234567"})
    assert (doc["status"], doc["lookups"]) == ("link_only", 2)


async def test_enrich_derives_link_and_cached_info_server_side(cat):
    await slab.lookup(cat, "ACE", "158690", transport=ace("ace_158690.html"))
    g = await slab.enrich_grading(cat, {"company": "ACE", "grade": 10, "cert_number": "158690",
                                        "report_url": "https://evil.example/", "cert_info": {"name": "fake"}})
    assert g["report_url"] == "https://acegrading.com/cert/158690" and g["cert_info"]["name"] == "Radiant Charizard"
    none = await slab.enrich_grading(cat, {"company": "PSA", "grade": 9, "cert_number": "56941091"})
    assert none["report_url"] == "https://www.psacard.com/cert/56941091/psa" and none["cert_info"] is None
    assert await slab.enrich_grading(cat, {"company": "OTHER", "grade": 9, "cert_number": None}) == {
        "company": "OTHER", "grade": 9, "cert_number": None}


@pytest.fixture
def phone(monkeypatch):
    monkeypatch.setattr(settings, "lan_gate_secret", "s3cret")
    monkeypatch.setattr(settings, "lan_origin", "https://localhost")
    return {"x-moc-gate": "s3cret"}


async def test_add_stores_report_url_and_cert_info_and_duplicate_guard_stays(cat, monkeypatch):
    await slab.lookup(cat, "ACE", "158690", transport=ace("ace_158690.html"))
    body = {"card_id": "pokemon:pgo-11", "grading": {"company": "ACE", "grade": 10, "cert_number": "158690"}}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        a = await c.post("/api/scan/add", json=body)
        b = await c.post("/api/scan/add", json=body)
    g = a.json()["stack"]["grading"]
    assert g["report_url"] == "https://acegrading.com/cert/158690" and g["cert_info"]["tier"] == "GEM MINT"
    assert b.json()["stack"]["duplicate"] is True and await cat.collection_items.count_documents({}) == 1


async def test_cert_api_allowed_through_the_phone_gate(cat, phone, monkeypatch):
    async def fake(db, grader, cert, **kw):
        return {"cert": {"status": "found"}, "cards": [], "how_exact": "none", "cached": False,
                "needs_confirm": False, "report_url": None}
    monkeypatch.setattr("app.services.slab.lookup", fake)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        r = await c.get("/api/scan/cert", params={"grader": "ACE", "cert": "158690"}, headers=phone)
        assert r.status_code == 200 and r.json()["cert"]["status"] == "found"
        assert (await c.get("/api/scan/cert", params={"grader": "ACE"}, headers=phone)).status_code == 422


# --- set-first token matching (slice 3b): one test per noise class, values from real captures where possible ---

SETS3 = {"sv4pt5": ("Paldean Fates", 2024, 91), "sv1": ("Scarlet & Violet", 2023, 198), "sv3pt5": ("151", 2023, 165),
         "swsh12pt5": ("Crown Zenith", 2023, 159), "base1": ("Base", 1999, 102), "g1": ("Generations", 2016, 83),
         "pgo": ("Pokemon GO", 2022, 78)}


async def put(db, set_id, num, name, rarity=None):
    nm, year, total = SETS3[set_id]
    c = card(set_id, num, name, rarity=rarity)
    c["set"].update(name=nm, printed_total=total, release_date=now().replace(year=year))
    await db.cards.insert_one(c)


@pytest.fixture
async def real(db):
    slab.reset_sets_cache()
    for sid, num, name, rar in [
            ("sv4pt5", "29", "Gardevoir ex", "Double Rare"), ("sv4pt5", "217", "Gardevoir ex", "Illustration Rare"),
            ("sv4pt5", "233", "Gardevoir ex", "Special Illustration Rare"), ("sv4pt5", "86", "Gardevoir", "Rare"),
            ("sv1", "86", "Gardevoir ex", "Double Rare"), ("sv3pt5", "205", "Mew ex", "Hyper Rare"),
            ("sv3pt5", "151", "Mew ex", "Double Rare"), ("sv3pt5", "7", "Squirtle", "Common"),
            ("swsh12pt5", "50", "Mr. Mime", "Common"), ("g1", "61", "Mr. Mime", "Rare"),
            ("base1", "27", "Farfetch'd", "Common"), ("g1", "27", "Farfetch'd", "Common"),
            ("swsh12pt5", "9", "Pikachu", "Common"), ("swsh12pt5", "10", "Pikachu V", "Rare Holo V"),
            ("swsh12pt5", "11", "Pikachu VMAX", "Rare Holo VMAX"), ("base1", "58", "Pikachu", "Common"),
            ("base1", "4", "Charizard", "Rare Holo"), ("sv3pt5", "6", "Charizard ex", "Double Rare"),
            ("sv3pt5", "20", "Flabébé", "Common"), ("pgo", "11", "Radiant Charizard", "Radiant Rare")]:
        await put(db, sid, num, name, rar)
    return db


def ids(cards):
    return [c["id"] for c in cards]


async def test_bgs_gardevoir_ex_sir_real_capture_picks_the_sir_print(real):
    i = info("BGS", cert="0018969667", name="Gardevoir ex SIR", year=2024,
             set_name="2024 Pokemon Scarlet and Violet Paldean Fates")
    assert await slab.resolve_sets(real, i) == ["sv4pt5"]  # not Scarlet & Violet: more words + the year
    cards = await slab.match_catalog(real, i)
    assert ids(cards)[0] == "pokemon:sv4pt5-233" and "rarity" in cards[0]["signals"]
    assert set(ids(cards)) == {"pokemon:sv4pt5-29", "pokemon:sv4pt5-217", "pokemon:sv4pt5-233"}  # longest name only
    assert slab.how_exact("BGS", cards) == "likely"


async def test_bgs_without_rarity_word_stays_possible(real):
    i = info("BGS", name="Gardevoir ex", year=2024, set_name="2024 Pokemon Scarlet and Violet Paldean Fates")
    assert slab.how_exact("BGS", await slab.match_catalog(real, i)) == "possible"


async def test_psa_mew_ex_205_real_capture(real):
    i = info("PSA", cert="168766783", name="MEW ex", number="205", year=2023, set_name="POKEMON MEW EN-151",
             variant="HYPER RARE", grade=9.0, tier="MINT")
    assert await slab.resolve_sets(real, i) == ["sv3pt5"]
    cards = await slab.match_catalog(real, i)
    assert ids(cards)[0] == "pokemon:sv3pt5-205" and {"name", "number", "set", "year", "rarity"} <= set(cards[0]["signals"])
    assert slab.how_exact("PSA", cards) == "likely"


async def test_ace_radiant_charizard_real_capture_set_first(real):
    i = info("ACE", name="Radiant Charizard", number="011/078", printed_total=78, year=2022, set_name="POKEMON GO",
             variant="HOLO")
    cards = await slab.match_catalog(real, i)
    assert ids(cards) == ["pokemon:pgo-11"] and cards[0]["signals"][:3] == ["name", "number", "total"]


@pytest.mark.parametrize("page_name, want", [
    ("Gardevoir ex SIR", "Gardevoir ex"), ("GARDEVOIR EX HOLO", "Gardevoir ex"), ("1st Edition Charizard", "Charizard"),
    ("Charizard Holo Shadowless Unlimited", "Charizard"), ("Mr. Mime", "Mr. Mime"), ("MR MIME", "Mr. Mime"),
    ("Mr Mime Reverse Holo", "Mr. Mime"), ("Farfetch'd", "Farfetch'd"), ("FARFETCHD", "Farfetch'd"),
    ("Pikachu VMAX", "Pikachu VMAX"), ("PIKACHU-V", "Pikachu V"), ("Pikachu", "Pikachu"), ("Flabebe", "Flabébé"),
    ("FLABÉBÉ Full Art", "Flabébé"), ("Charizard EX", "Charizard ex")])
async def test_name_noise_classes_match_the_right_catalog_name(real, page_name, want):
    cards = await slab.match_catalog(real, info("PSA", name=page_name))
    assert cards and {c["name"] for c in cards} == {want}, (page_name, [c["name"] for c in cards])


async def test_set_narrows_between_prints_of_one_name(real):
    for sid, set_name, year in [("base1", "POKEMON BASE SET", 1999), ("g1", "POKEMON GENERATIONS", 2016)]:
        cards = await slab.match_catalog(real, info("PSA", name="FARFETCH'D", set_name=set_name, year=year))
        assert ids(cards)[0] == f"pokemon:{sid}-27" and "set" in cards[0]["signals"]


async def test_word_page_names_leave_no_phantom_name_signal(real):
    # page says VMAX; only Pikachu V / Pikachu exist in that pool -> never "exact name" for the shorter card
    await real.cards.delete_one({"_id": "pokemon:swsh12pt5-11"})
    cards = await slab.match_catalog(real, info("PSA", name="Pikachu VMAX", set_name="Crown Zenith"))
    assert cards and all("name" not in c["signals"] for c in cards) and slab.how_exact("PSA", cards) == "possible"


async def test_unknown_set_falls_back_to_global_name_match(real):
    cards = await slab.match_catalog(real, info("PSA", name="Squirtle", set_name="Some Brand New Expansion"))
    assert ids(cards) == ["pokemon:sv3pt5-7"]


async def test_japanese_page_does_not_crash_and_uses_number_fallback(real):
    i = info("ACE", name="リザードン", number="027/083", printed_total=83, set_name="ジェネレーションズ", language="Japanese")
    assert await slab.resolve_sets(real, i) == []
    assert ids(await slab.match_catalog(real, i)) == ["pokemon:g1-27"]


def test_page_rarity_and_words():
    assert slab.page_rarity("Gardevoir ex SIR") == frozenset({"special", "illustration", "rare"})
    assert slab.page_rarity("MEW ex", "HYPER RARE") == frozenset({"hyper", "rare"})
    assert slab.page_rarity("Secret Rare Pikachu") == frozenset({"secret", "rare"})
    assert slab.page_rarity("Pikachu", "HOLO") is None
    assert slab.words("Farfetch'd Flabébé") == ["farfetchd", "flabebe"]


async def test_rarity_is_a_bonus_never_a_filter(real):
    i = info("PSA", name="Gardevoir ex SIR", year=2024, set_name="Paldean Fates")
    await real.cards.update_many({"set.id": "sv4pt5"}, {"$set": {"rarity": "Something Else"}})
    cards = await slab.match_catalog(real, i)
    assert len(cards) == 3 and all("rarity" not in c["signals"] for c in cards)


# --- misread warnings (slice 3c) ---

def codes(w):
    return [x["code"] for x in w]


async def test_warnings_grade_and_tier_mismatch(real):
    i = info("PSA", cert="168766783", name="MEW ex", number="205", set_name="POKEMON MEW EN-151", grade=9.0, tier="MINT")
    cards = await slab.match_catalog(real, i)
    assert slab.warnings(i, cards, 9.0, "MINT") == []
    assert codes(slab.warnings(i, cards, 10.0, "GEM MINT")) == ["grade_mismatch", "tier_mismatch"]
    assert slab.warnings(info("PSA", cert="12345678", grade=10, tier="GEM MT"), cards, 10.0, "Gem Mint") == []


async def test_warnings_non_pokemon_page_hank_aaron(real):
    i = info("PSA", cert="2023151", name="HANK AARON", set_name="1976 O-PEE-CHEE BASEBALL", year=1976, grade=8.0)
    w = slab.warnings(i, await slab.match_catalog(real, i))
    assert codes(w) == ["cert_length", "not_pokemon"] and "HANK AARON" in w[1]["text"]


async def test_warnings_not_raised_for_pokemon_without_catalog_hit(real):
    i = info("ACE", cert="158678", name="Charizard V", set_name="Star Birth", language="Japanese", variant="Special Art")
    assert "not_pokemon" in codes(slab.warnings(i, []))  # no Pokemon word anywhere: flagged
    j = info("PSA", cert="12345678", name="Unknown Mon", set_name="POKEMON SOME SET")
    assert slab.warnings(j, []) == []


def test_warnings_cert_length_per_grader():
    assert codes(slab.warnings(info("ACE", cert="1234567890", status="not_found"), [])) == ["cert_length"]
    assert slab.warnings(info("BGS", cert="0018969667", status="not_found"), []) == []
    assert codes(slab.warnings(info("BGS", cert="18969667", status="not_found"), [])) == ["cert_length"]


async def test_lookup_returns_warnings_and_api_passes_label(cat):
    got = await slab.lookup(cat, "ACE", "158690", transport=ace("ace_158690.html"), label_grade=9.0, label_tier="MINT")
    assert codes(got["warnings"]) == ["grade_mismatch", "tier_mismatch"]
    assert (await slab.lookup(cat, "ACE", "158690", transport=ace("ace_158690.html"), label_grade=10.0))["warnings"] == []


async def test_certs_recent_is_laptop_only_and_explains_the_match(real, phone):
    await slab.lookup(real, "ACE", "158690", transport=ace("ace_158690.html"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        r = await c.get("/api/scan/certs/recent")
        assert r.status_code == 200 and r.json()[0]["cert"] == "158690"
        assert r.json()[0]["match"]["top"][0]["id"] == "pokemon:pgo-11" and r.json()[0]["match"]["sets"] == ["pgo"]
        assert (await c.get("/api/scan/certs/recent", headers=phone)).status_code in (403, 404)
