import httpx

from fetcher.api import build_app
from fetcher.service import FetchService
from tests.conftest import Clock, FakeDriver, FakePage, make_cfg

URL = "https://www.pricecharting.com/game/x/y"


async def client(tmp_path, *pages):
    c = Clock()
    s = FetchService(make_cfg(tmp_path), FakeDriver(*pages), c, c.sleep, 0)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app(s)), base_url="http://t")


async def test_fetch_ok_and_status(tmp_path):
    async with await client(tmp_path, FakePage([("T", URL)])) as c:
        r = await c.post("/fetch/pricecharting", json={"url": URL})
        assert r.status_code == 200 and r.json()["status"] == "ok"
        st = (await c.get("/status")).json()
        assert st["browser"] == "up" and st["sites"]["pricecharting"] == "idle"
        assert (await c.get("/health")).json()["ok"] is True
        assert (await c.post("/close")).status_code == 200
        assert (await c.get("/status")).json()["browser"] == "down"


async def test_validation(tmp_path):
    async with await client(tmp_path) as c:
        assert (await c.post("/fetch/pricecharting", json={"url": "https://evil.com"})).status_code == 422
        assert (await c.post("/fetch/nope", json={"url": URL})).status_code == 422
        assert (await c.post("/fetch/altxyz", json={})).status_code == 422
        assert (await c.post("/fetch/altxyz", json={"url": "https://alt.xyz", "timeout_s": 9999})).status_code == 422
        assert (await c.post("/fetch/altxyz", json={"url": "https://alt.xyz", "click_labels": ["x"] * 11})).status_code == 422
        for n in (0, 11):
            assert (await c.post("/fetch/altxyz", json={"url": "https://alt.xyz", "pages": n})).status_code == 422


async def test_pages_passthrough(tmp_path):
    p = FakePage([("T", "https://alt.xyz/browse")], pages=["<a/>", "<b/>"])
    async with await client(tmp_path, p) as c:
        r = await c.post("/fetch/altxyz", json={"url": "https://alt.xyz/browse", "wait_selector": "a",
                                                "pages": 2, "next_label": "Go to next page"})
        assert r.json()["htmls"] == ["<a/>", "<b/>"] and r.json()["html"] == "<a/>"


async def test_health_lists_sites_and_reads_file_per_request(tmp_path):
    import json
    from fetcher.config import Settings
    c = Clock()
    cfg = Settings(failures_dir=tmp_path / "f", profile_dir=tmp_path / "p", sites_file=tmp_path / "sites.json")
    s = FetchService(cfg, FakeDriver(FakePage([("T", "https://www.cgccards.com/x")])), c, c.sleep, 0)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app(s)), base_url="http://t") as cl:
        ids = (await cl.get("/health")).json()["sites"]
        assert "psa" in ids and "beckett" in ids and "cgc" not in ids
        r = await cl.post("/fetch/cgc", json={"url": "https://www.cgccards.com/x"})
        assert r.status_code == 422
        (tmp_path / "sites.json").write_text(json.dumps([{"id": "cgc", "hosts": ["cgccards.com"]}]))
        assert "cgc" in (await cl.get("/health")).json()["sites"]      # no restart
        r = await cl.post("/fetch/cgc", json={"url": "https://www.cgccards.com/x"})
        assert r.status_code == 200 and r.json()["status"] == "ok"
