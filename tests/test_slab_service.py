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


def test_name_forms_cover_printed_spellings():
    assert "blastoise ex" in slab.name_forms("BLASTOISE-EX")
    assert slab.name_forms("Charizard Holo")[0] == "charizard"
    assert "radiant charizard" in slab.name_forms("RADIANT CHARIZARD 1st Edition")


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
