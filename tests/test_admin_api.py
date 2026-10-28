import httpx
import pytest

from app.main import app
from app.services import jobs


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


@pytest.mark.parametrize("path,type_", [
    ("/api/admin/catalog/import", "catalog_import"),
    ("/api/admin/catalog/import/retry-failed", "catalog_import"),
    ("/api/admin/prices/refresh", "price_refresh"),
    ("/api/admin/prices/fetch", "price_fetch"),
])
async def test_409_while_running(client, db, path, type_):
    await jobs.start(db, type_)
    r = await client.post(path, json={"owned": True} if type_ == "price_fetch" else None)
    assert r.status_code == 409 and "already running" in r.json()["detail"]


async def test_retry_failed_without_failures_starts_nothing(client, db):
    r = await client.post("/api/admin/catalog/import/retry-failed")
    assert r.status_code == 202 and r.json() == {"started": False, "sets": []}
    assert await db.jobs.count_documents({}) == 0
