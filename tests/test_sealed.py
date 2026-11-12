from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from app.db import migrate_sealed_v1
from app.db.models import SealedIn
from app.main import app
from app.providers.price import cardmarket, pricecharting
from app.providers.price.match import pick
from app.services import collection as coll, listing_pack, matching, refresh, sealed
from app.services.pricing import store_scraped_points
from app.services.search import build_query, exclude_sealed
from app.services.sets import sets_with_stats
from app.services.snapshots import take_snapshot
from tests.conftest import make_card
from tests.test_alerts import day, pt

FIX = Path(__file__).parent / "fixtures" / "pricecharting"
SET = {"_id": "pokemon:sv3", "tcg": "pokemon", "external_id": "sv3", "name": "Obsidian Flames", "series": "Scarlet & Violet",
       "release_date": datetime(2023, 8, 11, tzinfo=timezone.utc), "logo_url": "https://x/logo.png", "ptcgo_code": "OBF"}
BOX = dict(set_id="sv3", type="booster_box")


@pytest.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        yield c


async def seed_set(db):
    await db.sets.insert_one(dict(SET))


async def test_entry_is_created_once_and_linked_to_the_set(db):
    await seed_set(db)
    a = await sealed.ensure_entry(db, SealedIn(**BOX))
    b = await sealed.ensure_entry(db, SealedIn(**BOX))
    assert a["_id"] == b["_id"] == "sealed:pokemon:en:sv3:booster_box" and await db.cards.count_documents({}) == 1
    assert (a["kind"], a["name"], a["set"]["name"], a["set"]["ref_id"], a["set"]["id"]) == (
        "sealed", "Obsidian Flames Booster Box", "Obsidian Flames", "sv3", "sealed:sv3")
    assert a["images"]["small"] == "https://x/logo.png" and a["rarity"] == "Booster Box"
    e = await sealed.ensure_entry(db, SealedIn(**BOX, edition="Pokémon Center"))
    assert e["_id"].endswith(":booster_box:pokemon-center") and e["name"] == "Obsidian Flames Booster Box (Pokémon Center)"


async def test_entry_is_price_schema_2_so_boot_migration_leaves_prices_alone(db):
    from app.db import migrate_prices_v2
    await seed_set(db)
    e = await sealed.ensure_entry(db, SealedIn(**BOX))
    await store_scraped_points(db, e["_id"], [pt(36893)], day())
    before = (await db.cards.find_one({"_id": e["_id"]}))["latest_price"]
    await migrate_prices_v2._migrate_cards(db)
    assert (await db.cards.find_one({"_id": e["_id"]}))["latest_price"] == before


async def test_set_must_exist(db):
    with pytest.raises(HTTPException) as e:
        await sealed.ensure_entry(db, SealedIn(set_id="nope", type="etb"))
    assert e.value.status_code == 404
    await seed_set(db)
    with pytest.raises(HTTPException):                       # an English set is not a Japanese one
        await sealed.ensure_entry(db, SealedIn(**BOX, language="ja"))


async def test_add_makes_a_normal_stack_and_merges_copies(db):
    await seed_set(db)
    a = await sealed.add(db, SealedIn(**BOX, quantity=2, acquired={"type": "purchased", "price": 12000}))
    b = await sealed.add(db, SealedIn(**BOX))
    assert a["id"] == b["id"] and b["quantity"] == 3 and b["condition"] == "NM"
    assert await db.collection_items.count_documents({}) == 1 and b["entry"]["name"] == "Obsidian Flames Booster Box"


async def test_sealed_never_leaks_into_card_search_or_set_counts(db):
    await seed_set(db)
    await db.cards.insert_one(make_card("sv3", "1"))
    await sealed.ensure_entry(db, SealedIn(**BOX))
    flt = exclude_sealed(build_query("obsidian"))
    names = [c["name"] async for c in db.cards.find(flt)]
    assert "Obsidian Flames Booster Box" not in names
    assert await db.cards.count_documents(exclude_sealed(build_query(None))) == 1
    [s] = [s for s in await sets_with_stats(db) if s["external_id"] == "sv3"]
    assert s["cards_total"] == 1                                   # the box is not a card of the set
    assert [e["name"] for e in await sealed.list_entries(db, "booster")] == ["Obsidian Flames Booster Box"]


async def test_valuation_keeps_sealed_out_of_card_totals(db):
    await seed_set(db)
    card = make_card("sv3", "1")
    await db.cards.insert_one(card)
    await store_scraped_points(db, card["_id"], [pt(10000)], day())
    await db.collection_items.insert_one({"card_id": card["_id"], "variant": None, "language": "en", "condition": "NM",
                                          "grading": None, "quantity": 1, "stack_key": "c", "created_at": datetime.now(timezone.utc)})
    s = await sealed.add(db, SealedIn(**BOX, quantity=2, acquired={"type": "purchased", "price": 12000}))
    unpriced = await sealed.summary(db)
    assert (unpriced["value"], unpriced["unpriced"], unpriced["units"], unpriced["cost"]) == (0, 1, 2, 24000)
    await store_scraped_points(db, s["card_id"], [pt(36893)], day())          # $368.93 raw -> EUR via 0.9
    cards = await coll.valuate(db)
    assert [r["item"]["card_id"] for r in cards] == [card["_id"]] and cards[0]["value"] == 9000
    [row] = await coll.valuate(db, kind="sealed")
    assert row["value"] == round(36893 * 0.9) * 2 and (await sealed.summary(db))["unpriced"] == 0
    assert len(await coll.valuate(db, kind="all")) == 2


async def test_snapshot_total_is_cards_only(db):
    await seed_set(db)
    s = await sealed.add(db, SealedIn(**BOX))
    await store_scraped_points(db, s["card_id"], [pt(10000)], day())
    snap = await take_snapshot(db)
    assert snap["total_value"] == 0 and snap["item_count"] == 0 and snap["sealed_value"] == 9000


async def test_api_add_list_and_collection_kind(db, client):
    await seed_set(db)
    r = await client.post("/api/sealed", json={**BOX, "quantity": 2})
    assert r.status_code == 201 and r.json()["entry"]["sealed_type"] == "booster_box"
    assert (await client.post("/api/sealed", json={"set_id": "zzz", "type": "tin"})).status_code == 404
    assert (await client.post("/api/sealed", json={**BOX, "type": "bogus"})).status_code == 422
    assert [t["value"] for t in (await client.get("/api/sealed/types")).json()][:2] == ["booster_box", "booster_bundle"]
    assert len((await client.get("/api/sealed?q=obsidian")).json()) == 1
    assert (await client.get("/api/collection")).json()["items"] == []
    items = (await client.get("/api/collection?kind=sealed")).json()["items"]
    assert len(items) == 1 and items[0]["card"]["kind"] == "sealed" and items[0]["quantity"] == 2
    summ = (await client.get("/api/collection/summary")).json()
    assert summ["sealed"]["units"] == 2 and summ["distinct"] == 0
    assert (await client.get("/api/collection/facets?kind=sealed")).status_code == 200


def sealed_card():
    return {"_id": "sealed:pokemon:en:sv3:booster_box", "kind": "sealed", "name": "Obsidian Flames Booster Box", "number": "",
            "language": "en", "set": {"name": "Obsidian Flames"}}


def test_pricecharting_search_and_pick_from_a_real_page():
    html = (FIX / "search_sealed_obsidian_flames_booster_box.html").read_text()
    cands = pricecharting.parse_search(html)
    assert [c.title for c in cands] == ["Booster Box", "Half Booster Box"]
    best, ranked = pick(sealed_card(), cands)
    assert best and best.title == "Booster Box" and ranked[0].score > ranked[1].score
    other = {**sealed_card(), "name": "Obsidian Flames Elite Trainer Box"}
    assert pick(other, cands)[0] is None
    url = pricecharting.search_url(sealed_card()).lower()
    assert "booster+box" in url and "q=pokemon+obsidian+flames" in url


def test_pricecharting_sealed_product_page_prices():
    html = (FIX / "product_sealed_obsidian_flames_booster_box.html").read_text()
    r = pricecharting.parse_product(html, "https://www.pricecharting.com/game/pokemon-obsidian-flames/booster-box", datetime.now(timezone.utc).date())
    raw = [p for p in r.points if p["grade_key"] == "raw" and p["kind"] == "market"]
    assert r.status == "ok" and raw[0]["market"] == 36893 and raw[0]["currency"] == "USD"


async def test_cardmarket_sealed_needs_the_page_url_once(db):
    class NoFetch:
        async def fetch(self, *a, **k):
            raise AssertionError("must not search")
    res = await cardmarket.CardmarketProvider().fetch(sealed_card(), NoFetch(), None)
    assert res.status == "needs_match" and "paste" in res.detail
    assert matching.validate_url("cardmarket_web", "https://www.cardmarket.com/en/Pokemon/Products/Booster-Boxes/Obsidian-Flames/Booster-Box")
    with pytest.raises(matching.InvalidMatch):
        matching.validate_url("cardmarket_web", "https://www.cardmarket.com/en/Pokemon/Products/Search?searchString=x")


async def test_catalog_refresh_skips_sealed(db):
    await seed_set(db)
    s = await sealed.add(db, SealedIn(**BOX))
    out = await refresh.refresh_card_price(db, s["card_id"])
    assert out["found"] is False and out["prices"] == 0


async def test_listing_pack_for_sealed(db):
    await seed_set(db)
    s = await sealed.add(db, SealedIn(**BOX, quantity=2))
    await store_scraped_points(db, s["card_id"], [pt(10000)], day())
    await db.photos.insert_one({"stack_id": s["id"], "order": 0, "cover": True, "kind": "front", "data": b"x", "thumb": b"x",
                                  "w": 1, "h": 1, "bytes": 1, "created_at": datetime.now(timezone.utc)})
    pack = await listing_pack.build_pack(db, [s["id"]], "vinted")
    [p] = pack["items"]
    assert p["title"] == "Obsidian Flames Booster Box - sealed" and "factory sealed" in p["description"]
    assert (p["vinted_condition"], p["vinted_parcel"], p["sealed"]) == ("New with tags", "medium", True)
    cm = await listing_pack.build_pack(db, [s["id"]], "cardmarket")
    assert any(w.startswith("slab") for w in cm["items"][0]["warnings"])


async def test_migration_moves_sealed_products_and_keeps_a_backup(db):
    await seed_set(db)
    await db.products.insert_many([
        {"name": "Box", "type": "booster_box", "set_name": "Obsidian Flames", "language": "en", "quantity": 2, "status": "sealed",
         "purchase_price": 12000, "market_value": 14500, "purchased_from": "shop", "purchase_date": "2026-11-01"},
        {"name": "Old", "type": "tin", "set_name": "Obsidian Flames", "language": "en", "quantity": 1, "status": "opened"}])
    assert await migrate_sealed_v1.migrate(db) == {"moved": 1, "left": 0}
    [it] = await db.collection_items.find().to_list(None)
    assert it["quantity"] == 2 and it["acquired"]["price"] == 12000 and it["acquired"]["source"] == "shop"
    names = await db.list_collection_names()
    assert "products" not in names and "products_slice1_backup" in names
    assert await migrate_sealed_v1.migrate(db) == {"moved": 0, "left": 0}      # no-op afterwards


async def test_migration_leaves_products_whose_set_is_unknown(db):
    await db.products.insert_one({"name": "Box", "type": "etb", "set_name": "Made Up Set", "language": "en", "quantity": 1, "status": "sealed"})
    assert await migrate_sealed_v1.migrate(db) == {"moved": 0, "left": 1}
    assert "products" in await db.list_collection_names() and await db.collection_items.count_documents({}) == 0
