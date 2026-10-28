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
