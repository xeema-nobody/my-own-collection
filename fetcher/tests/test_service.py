import pytest

from fetcher.service import FetchRejected, FetchService
from tests.conftest import Clock, FakeDriver, FakePage, make_cfg

URL = "https://www.pricecharting.com/game/x/y"
OK = ("Mew ex", URL)


def svc(tmp_path, *pages, **cfg):
    c = Clock()
    d = FakeDriver(*pages)
    return FetchService(make_cfg(tmp_path, **cfg), d, c, c.sleep, jitter_s=0), d, c


async def test_ok_anonymous(tmp_path):
    p = FakePage([OK])
    s, d, _ = svc(tmp_path, p)
    r = await s.fetch("pricecharting", URL)
    assert r.status == "ok" and r.html == "<html>ok</html>"
    assert not p.fronted and p.closed and p.gotos == [URL]
    assert s.status()["sites"]["pricecharting"] == "idle"


async def test_cookie_banner_clicked_for_cardmarket(tmp_path):
    u = "https://www.cardmarket.com/en/Pokemon/Products/Singles/x"
    p = FakePage([("Mew", u)])
    s, *_ = svc(tmp_path, p)
    await s.fetch("cardmarket", u)
    assert p.clicked == ["ONLY REQUIRED"]


async def test_challenge_resolves_without_user(tmp_path):
    u = "https://www.cardmarket.com/en/Pokemon/Products/Singles/x"
    p = FakePage([("Just a moment...", u)] * 3 + [("Mew", u)])
    s, *_ = svc(tmp_path, p)
    r = await s.fetch("cardmarket", u)
    assert r.status == "ok" and not p.fronted     # within grace: no user prompt


async def test_login_wait_then_resume(tmp_path):
    login = "https://alt.xyz/login"
    p = FakePage([("Log in", login)] * 4 + [("Browse", "https://alt.xyz/browse")])
    s, *_ = svc(tmp_path, p)
    seen = []
    orig = p.bring_to_front

    async def spy():
        seen.append(s.status()["sites"]["altxyz"])
        await orig()

    p.bring_to_front = spy
    r = await s.fetch("altxyz", "https://alt.xyz/browse?query=a")
    assert seen == ["waiting_login:altxyz"]
    assert r.status == "ok" and p.fronted
    assert len(p.gotos) == 2                       # reloaded wanted URL after login


async def test_login_timeout(tmp_path):
    p = FakePage([("Log in", "https://alt.xyz/login")])
    s, *_ = svc(tmp_path, p, login_timeout_s=20, challenge_grace_s=5)
    r = await s.fetch("altxyz", "https://alt.xyz/browse")
    assert r.status == "login_timeout" and p.shots and p.closed
    assert s.status()["sites"]["altxyz"] == "idle"


async def test_challenge_never_clears_is_blocked(tmp_path):
    u = "https://www.cardmarket.com/x"
    p = FakePage([("Attention Required | Cloudflare", u)])
    s, *_ = svc(tmp_path, p, login_timeout_s=10, challenge_grace_s=5)
    r = await s.fetch("cardmarket", u)
    assert r.status == "login_timeout" and p.fronted   # user was asked, did not clear


async def test_rejects_bad_site_and_host(tmp_path):
    s, *_ = svc(tmp_path)
    with pytest.raises(FetchRejected):
        await s.fetch("nope", URL)
    with pytest.raises(FetchRejected):
        await s.fetch("pricecharting", "https://evil.com/")


async def test_error_gives_screenshot_and_closes_page(tmp_path):
    p = FakePage([OK])

    async def boom(url, t):
        raise TimeoutError("nav")

    p.goto = boom
    s, *_ = svc(tmp_path, p)
    r = await s.fetch("pricecharting", URL)
    assert r.status == "error" and "nav" in r.detail and p.shots and p.closed
    assert s.status()["last_error"]


async def test_idle_reaper(tmp_path):
    p = FakePage([OK])
    s, d, c = svc(tmp_path, p, idle_timeout_s=120)
    await s.fetch("pricecharting", URL)
    assert d.up
    c.t += 60
    assert not await s.reap_idle() and d.up
    c.t += 61
    assert await s.reap_idle() and not d.up


async def test_click_text_then_ok(tmp_path):
    u = "https://alt.xyz/browse?query=a"
    p = FakePage([("Browse", u)])
    s, *_ = svc(tmp_path, p)
    r = await s.fetch("altxyz", u, click_text="Sold listings")
    assert r.status == "ok" and p.clicked == ["Sold listings"]


async def test_click_text_missing_is_error(tmp_path):
    u = "https://alt.xyz/browse?query=a"
    p = FakePage([("Browse", u)])
    p.click_ok = False
    s, *_ = svc(tmp_path, p)
    r = await s.fetch("altxyz", u, click_text="Sold listings")
    assert r.status == "error" and "Sold listings" in r.detail and p.shots
