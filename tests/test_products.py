import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.db.models import ProductIn, ProductPatch
from app.main import app
from app.services import products
from app.services.snapshots import take_snapshot


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


async def test_create_defaults_and_value_stamp(db):
    p = await products.create(db, ProductIn(name="Booster box", type="booster_box", quantity=2,
                                            purchase_price=12000, market_value=14500))
    assert (p["status"], p["tcg"], p["language"], p["quantity"]) == ("sealed", "pokemon", "en", 2)
    assert p["market_value_at"] is not None and p["sold_at"] is None
    bare = await products.create(db, ProductIn(name="Mystery tin"))
    assert bare["market_value"] is None and bare["market_value_at"] is None and bare["purchase_price"] is None


def test_validation_rejects_zero_price_and_bad_quantity():
    with pytest.raises(ValidationError):
        ProductIn(name="x", market_value=0)
    with pytest.raises(ValidationError):
        ProductIn(name="x", purchase_price=0)
    with pytest.raises(ValidationError):
        ProductIn(name="x", quantity=0)
    with pytest.raises(ValidationError):
        ProductIn(name="", quantity=1)


async def test_patch_stamps_and_clears(db):
    p = await products.create(db, ProductIn(name="ETB", type="etb"))
    p = await products.patch(db, p["id"], ProductPatch(market_value=5000))
    assert p["market_value"] == 5000 and p["market_value_at"]
    p = await products.patch(db, p["id"], ProductPatch(market_value=None))
    assert p["market_value"] is None and p["market_value_at"] is None
    p = await products.patch(db, p["id"], ProductPatch(status="sold_sealed", sold_price=6000))
    assert p["status"] == "sold_sealed" and p["sold_at"] and p["sold_price"] == 6000
    with pytest.raises(HTTPException) as e:
        await products.patch(db, p["id"], ProductPatch.model_validate({"quantity": None}))
    assert e.value.status_code == 422


async def test_unknown_id_404(db):
    for call in (products.remove(db, "0" * 24), products.patch(db, "0" * 24, ProductPatch(note="x")),
                 products.remove(db, "nope")):
        with pytest.raises(HTTPException) as e:
            await call
        assert e.value.status_code == 404


async def test_list_filters(db):
    await products.create(db, ProductIn(name="a", type="etb"))
    await products.create(db, ProductIn(name="b", type="tin", status="opened"))
    assert [p["name"] for p in await products.list_(db, status="opened")] == ["b"]
    assert [p["name"] for p in await products.list_(db, type_="etb")] == ["a"]
    assert len(await products.list_(db)) == 2


async def test_summary_counts_only_sealed_and_never_zero_fills(db):
    await products.create(db, ProductIn(name="box", quantity=2, purchase_price=12000, market_value=14500))
    await products.create(db, ProductIn(name="unknown", quantity=3))                     # no value, no cost
    await products.create(db, ProductIn(name="opened", status="opened", market_value=9999, purchase_price=1000))
    await products.create(db, ProductIn(name="sold", status="sold_sealed", market_value=9999))
    assert await products.summary(db) == {"value": 29000, "cost": 24000, "stacks": 2, "units": 5,
                                          "unpriced": 1, "cost_missing": 1}


async def test_api_round_trip(db, client):
    r = await client.post("/api/products", json={"name": "Box", "type": "booster_box", "quantity": 2,
                                                 "purchase_price": 12000, "market_value": 14500,
                                                 "purchase_date": "2026-11-01"})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["purchase_date"] == "2026-11-01"
    assert (await client.get("/api/products/summary")).json()["value"] == 29000
    r = await client.patch(f"/api/products/{pid}", json={"status": "opened"})
    assert r.json()["status"] == "opened"
    assert (await client.get("/api/products/summary")).json()["value"] == 0
    assert len((await client.get("/api/products?status=opened")).json()) == 1
    assert (await client.delete(f"/api/products/{pid}")).status_code == 204
    assert (await client.delete(f"/api/products/{pid}")).status_code == 404
    assert (await client.post("/api/products", json={"name": "x", "market_value": 0})).status_code == 422


async def test_snapshot_carries_sealed_value_apart_from_cards(db):
    await products.create(db, ProductIn(name="box", market_value=5000))
    snap = await take_snapshot(db)
    assert snap["sealed_value"] == 5000 and snap["total_value"] == 0
