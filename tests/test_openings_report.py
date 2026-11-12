import httpx
import pytest

from app.main import app
from app.services import collection as coll
from app.services.pricing import store_scraped_points
from tests.test_alerts import day, pt
from tests.test_openings import PULL, box
from tests.conftest import make_card

BOXID = "sealed:pokemon:en:sv3:booster_box"


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


async def open_with(client, stack, pulled, qty=1):
    return (await client.post(f"/api/collection/{stack['id']}/open", json={"quantity": qty, "pulled": pulled})).json()


async def test_empty_report(db, client):
    r = await client.get("/api/openings/report")
    assert r.status_code == 200 and r.json()["openings"] == [] and r.json()["totals"]["net"] is None


async def test_net_roi_hits_and_kept_delta(db, client):
    s = await box(db, qty=2, cost=5000)
    await store_scraped_points(db, PULL, [pt(10000)], day())      # 9000 per copy
    await store_scraped_points(db, BOXID, [pt(10000)], day())     # kept sealed 9000 per unit
    await open_with(client, s, [{"card_id": PULL, "quantity": 2}])
    j = (await client.get("/api/openings/report")).json()
    [o] = j["openings"]
    assert (o["cost"], o["pulls_value"], o["net"]) == (5000, 18000, 13000) and o["roi"] == 2.6
    assert (o["hits"], o["hit_rate"], o["kept_value"], o["vs_kept"]) == (2, 1.0, 9000, 9000)
    assert o["best_hit"]["value"] == 9000
    [p] = j["products"]
    assert p["opened"]["net"] == 13000 and p["kept"]["units"] == 1 and p["sold"]["units"] == 0
    assert j["totals"]["net"] == 13000 and j["totals"]["vs_kept"] == 9000


async def test_unpriced_pull_not_zero_and_unknown_cost_gives_none(db, client):
    s = await box(db, cost=0)
    await db.cards.insert_one(make_card("sv3", "2", priced=False))
    j = await open_with(client, s, [{"card_id": "pokemon:sv3-2"}])
    [o] = (await client.get("/api/openings/report")).json()["openings"]
    assert o["unpriced"] == 1 and o["priced_copies"] == 0 and o["hit_rate"] is None
    assert o["pulls_value"] is None and o["cost"] is None and o["net"] is None


async def test_sold_sealed_aggregated(db, client):
    s = await box(db, qty=2, cost=10000)
    await coll.remove(db, s["id"], quantity=1, reason="sold", price=15000)
    [p] = (await client.get("/api/openings/report")).json()["products"]
    assert p["sold"] == {"units": 1, "proceeds": 15000, "realised": 5000} and p["kept"]["units"] == 1
