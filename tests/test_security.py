import httpx

from app.main import app


def client(host="localhost"):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"http://{host}")


async def test_cross_site_write_rejected():
    async with client() as c:
        r = await c.post("/api/alerts/evaluate", headers={"origin": "https://evil.example"})
        assert r.status_code == 403
        r = await c.post("/api/collection/import", content=b"{}", headers={"origin": "https://evil.example",
                                                                           "content-type": "text/plain"})
        assert r.status_code == 403


async def test_own_origin_and_no_origin_pass(db):
    async with client() as c:
        assert (await c.get("/health", headers={"origin": "https://evil.example"})).status_code == 200  # reads: CORS blocks the reply
        assert (await c.post("/api/alerts/evaluate", headers={"origin": "http://localhost:5180"})).status_code == 200
        assert (await c.post("/api/alerts/evaluate")).status_code == 200   # curl / scripts


async def test_rebound_host_rejected():
    async with client("evil.example") as c:
        assert (await c.get("/health")).status_code == 400


async def test_sale_url_must_be_http(db):
    from tests.conftest import make_card
    await db.cards.insert_one(make_card("a", "1"))
    async with client() as c:
        body = {"price": 100, "sold_at": "2026-01-01", "url": "javascript:alert(1)"}
        assert (await c.post("/api/cards/pokemon:a-1/sales", json=body)).status_code == 422
        assert (await c.post("/api/cards/pokemon:a-1/sales", json={**body, "url": "https://x.example/a"})).status_code == 201


async def test_jobs_limit_bounded(db):
    async with client() as c:
        assert (await c.get("/api/admin/jobs?limit=-1")).status_code == 422
        assert (await c.get("/api/admin/jobs?limit=1000")).status_code == 422
