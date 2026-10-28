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
        assert (await c.get("/health")).json() == {"ok": True}
        assert (await c.post("/close")).status_code == 200
        assert (await c.get("/status")).json()["browser"] == "down"


async def test_validation(tmp_path):
    async with await client(tmp_path) as c:
        assert (await c.post("/fetch/pricecharting", json={"url": "https://evil.com"})).status_code == 422
        assert (await c.post("/fetch/nope", json={"url": URL})).status_code == 422
        assert (await c.post("/fetch/altxyz", json={})).status_code == 422
        assert (await c.post("/fetch/altxyz", json={"url": "https://alt.xyz", "timeout_s": 9999})).status_code == 422
        assert (await c.post("/fetch/altxyz", json={"url": "https://alt.xyz", "click_labels": ["x"] * 11})).status_code == 422
