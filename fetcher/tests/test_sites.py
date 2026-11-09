from pathlib import Path

from fetcher.sites import SITES, PageState, is_challenge, needs_login

FX = Path(__file__).parents[2] / "tests" / "fixtures"


def st(title="x", url="https://alt.xyz/browse"):
    return PageState(title, url, "")


def test_challenge_titles():
    assert is_challenge(st("Just a moment..."))
    assert is_challenge(st("Attention Required | Cloudflare"))
    assert not is_challenge(st("Mew ex - Pokemon 151 | Cardmarket"))


def test_login_path():
    assert needs_login(st(url="https://alt.xyz/login?next=/browse"))
    assert needs_login(st(url="https://www.cardmarket.com/en/Pokemon/Login"))
    assert not needs_login(st(url="https://www.pricecharting.com/game/x/y"))


def test_host_whitelist():
    cm = SITES["cardmarket"]
    assert cm.allows("https://www.cardmarket.com/en/Pokemon")
    assert not cm.allows("https://evil.com/?u=cardmarket.com")
    assert not cm.allows("https://cardmarket.com.evil.com/")
    assert not cm.allows("file:///etc/passwd")


def test_fixtures_not_flagged_as_challenge():
    import re
    for rel in ("pricecharting/product_mew_ex_205.html", "cardmarket/product_mew_ex_205.html",
                "altxyz/sold_mew_ex_205.html"):
        html = (FX / rel).read_text()
        title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
        assert not is_challenge(st(title)), rel


def test_builtin_slab_sites():
    assert SITES["psa"].allows("https://www.psacard.com/cert/168766783/psa")
    assert SITES["beckett"].allows("https://beckett.com/grading/card-lookup?item_id=1&item_type=BGS")
    assert not SITES["psa"].allows("https://psacard.com.evil.com/")


def test_site_file_merge_and_bad_entries(tmp_path):
    import json
    from fetcher.sites import all_sites
    f = tmp_path / "sites.json"
    assert set(all_sites(tmp_path / "none.json")) == set(SITES)       # missing file = built-ins
    f.write_text("not json")
    assert set(all_sites(f)) == set(SITES)
    f.write_text(json.dumps([
        {"id": "cgc", "hosts": ["cgccards.com"], "min_interval_s": 4},
        {"id": "Bad Id", "hosts": ["x.com"]},
        {"id": "nohosts", "hosts": []},
        {"id": "evil", "hosts": ["http://x.com/"]},
        {"id": "psa", "hosts": ["psacard.com"], "min_interval_s": 0.01},   # file wins, gap floored
        "junk",
    ]))
    s = all_sites(f)
    assert s["cgc"].allows("https://www.cgccards.com/certlookup/123/") and s["cgc"].min_interval_s == 4
    assert "Bad Id" not in s and "nohosts" not in s and "evil" not in s
    assert s["psa"].min_interval_s == 1.0
