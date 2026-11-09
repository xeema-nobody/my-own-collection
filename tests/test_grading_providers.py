"""Cert providers on saved pages: parse, not found, blocked / fetcher down -> degrade, URL building, validation."""
from pathlib import Path

import httpx
import pytest

from app.providers.fetcher import FetcherClient
from app.providers.grading import registry
from app.providers.grading.ace import AceProvider
from app.providers.grading.base import clean_cert, split_number

FX = Path(__file__).parent / "fixtures" / "cert"


def page(name):
    return (FX / name).read_text()


def ace_transport(body, status=200):
    return httpx.MockTransport(lambda req: httpx.Response(status, text=body))


def fetcher_transport(sites=("psa", "beckett"), fetch=None, down=False):
    def handler(req: httpx.Request):
        if down:
            raise httpx.ConnectError("refused")
        if req.url.path == "/health":
            return httpx.Response(200, json={"ok": True, "sites": list(sites)})
        return httpx.Response(200, json=fetch)
    return httpx.MockTransport(handler)


def client(**kw):
    return FetcherClient("http://f", transport=fetcher_transport(**kw), unattended=True)


def test_clean_cert_digits_only():
    assert clean_cert(" #158690 ") == "158690"
    for bad in ("12 34", "../x", "1e5", "-5", "", None, "158690/../../x", "1234567890123"):
        assert clean_cert(bad) is None


def test_split_number():
    assert split_number("011/078") == ("011/078", 78)
    assert split_number("205") == ("205", None)
    assert split_number("SWSH285") == ("SWSH285", None)
    assert split_number("TG05/TG30") == ("TG05/TG30", 30)
    assert split_number("garbage!!") == (None, None)


async def test_ace_found():
    i = await AceProvider(ace_transport(page("ace_158690.html"))).lookup("158690")
    assert (i.status, i.name, i.number, i.printed_total, i.set_name, i.year, i.variant) == (
        "found", "Radiant Charizard", "011/078", 78, "Pokemon GO", 2022, "Holo")
    assert (i.grade, i.tier) == (10.0, "GEM MINT")
    assert i.subgrades == {"surface": 10.0, "centering": 10.0, "edges": 10.0, "corners": 10.0}
    assert i.population["same"] == 785 and i.population["submitted"] == 1475
    assert i.url == "https://acegrading.com/cert/158690"


async def test_ace_japanese_and_not_found():
    i = await AceProvider(ace_transport(page("ace_158678.html"))).lookup("158678")
    assert (i.name, i.number, i.printed_total, i.set_name, i.language, i.variant) == (
        "Charizard V", "103/100", 100, "Star Birth", "Japanese", "Special Art")
    n = await AceProvider(ace_transport(page("ace_notfound.html"))).lookup("999999")
    assert n.status == "not_found" and n.url == "https://acegrading.com/cert/999999"


async def test_ace_http_error_and_network_error_degrade():
    assert (await AceProvider(ace_transport("x", 503)).lookup("158690")).status == "unavailable"
    def boom(req):
        raise httpx.ConnectTimeout("t")
    i = await AceProvider(httpx.MockTransport(boom)).lookup("158690")
    assert i.status == "unavailable" and i.url.endswith("/158690")


async def test_psa_found_via_fetcher():
    fetch = {"status": "ok", "html": page("psa_168766783.html"), "final_url": "x"}
    i = await registry.lookup("PSA", "168766783", client=client(fetch=fetch))
    assert (i.status, i.name, i.number, i.printed_total, i.set_name, i.year) == (
        "found", "MEW ex", "205", None, "POKEMON MEW EN-151", 2023)
    assert (i.grade, i.tier, i.variant) == (9.0, "MINT", "HYPER RARE")
    assert i.population == {"same": 10278, "higher": 6059}
    assert i.url == "https://www.psacard.com/cert/168766783/psa"


async def test_psa_generic_subject_uses_title_and_no_grade_is_flagged():
    fetch = {"status": "ok", "html": page("psa_nograde_100000001.html")}
    i = await registry.lookup("PSA", "100000001", client=client(fetch=fetch))
    assert (i.status, i.name, i.number, i.year, i.grade, i.tier) == ("found", "CHARIZARD EX", "228", 2023, None, None)
    assert "no grade" in i.detail


async def test_psa_404_page_is_not_found():
    fetch = {"status": "ok", "html": page("psa_notfound.html")}
    i = await registry.lookup("PSA", "999999999", client=client(fetch=fetch))
    assert i.status == "not_found" and i.url.endswith("/999999999/psa")


async def test_bgs_no_record_page_is_not_found():
    fetch = {"status": "ok", "html": page("bgs_notfound.html")}
    assert (await registry.lookup("BGS", "0000000001", client=client(fetch=fetch))).status == "not_found"


async def test_psa_wrong_cert_on_page_is_not_found():
    fetch = {"status": "ok", "html": page("psa_168766783.html")}
    i = await registry.lookup("PSA", "168766780", client=client(fetch=fetch))
    assert i.status == "not_found"


async def test_bgs_found_via_fetcher():
    fetch = {"status": "ok", "html": page("bgs_0018969667.html")}
    i = await registry.lookup("BGS", "0018969667", client=client(fetch=fetch))
    assert (i.status, i.name, i.set_name, i.year, i.grade, i.number) == (
        "found", "Gardevoir ex SIR", "2024 Pokemon Scarlet and Violet Paldean Fates", 2024, 9.0, None)
    assert i.subgrades == {"centering": 9.0, "corners": 9.0, "edges": 10.0, "surface": 10.0}
    assert i.url == "https://beckett.com/grading/card-lookup?item_id=0018969667&item_type=BGS"


async def test_fetcher_blocked_down_and_missing_site_degrade_to_link():
    blocked = await registry.lookup("PSA", "168766783", client=client(fetch={"status": "blocked"}))
    assert blocked.status == "blocked" and blocked.url
    down = await registry.lookup("PSA", "168766783", client=client(down=True))
    assert down.status == "unavailable" and "fetcher.sh start" in down.detail and down.url
    old = await registry.lookup("BGS", "0018969667", client=client(sites=("psa",)))
    assert old.status == "unavailable" and "fetcher.sh restart" in old.detail and old.url
    err = await registry.lookup("PSA", "168766783", client=client(fetch={"status": "error", "detail": "timeout"}))
    assert err.status == "unavailable" and err.detail == "timeout"


async def test_challenge_page_is_not_parsed_as_a_card():
    fetch = {"status": "ok", "html": page("blocked_cloudflare_challenge.html")}
    assert (await registry.lookup("PSA", "168766783", client=client(fetch=fetch))).status == "not_found"


async def test_link_only_graders_and_invalid_input():
    cgc = await registry.lookup("CGC", "1234567")
    assert cgc.status == "link_only" and cgc.url == "https://www.cgccards.com/certlookup/1234567/"
    sgc = await registry.lookup("SGC", "1234567")
    assert sgc.status == "link_only" and sgc.url is None
    for g, c in (("PSA", "12a45678"), ("ACE", "1"), ("XYZ", "123456"), ("ACE", "../etc")):
        i = await registry.lookup(g, c)
        assert i.status == "invalid" and i.url is None


@pytest.mark.parametrize("raw,canon", [("beckett", "BGS"), ("psa", "PSA"), (" ace ", "ACE")])
def test_grader_aliases(raw, canon):
    assert registry.canon_grader(raw) == canon
