import uuid
from datetime import datetime, timedelta, timezone

from app.services import collection as coll
from app.services.pricing import get_rates, store_card_prices, store_scraped_points
from app.services.snapshots import take_snapshot
from conftest import make_card

UTC = timezone.utc
CID = "pokemon:a-1"


def item(grade=None, company="PSA", qty=1, variant="holofoil"):
    return {"card_id": CID, "variant": variant, "language": "en", "condition": None if grade else "NM",
            "grading": {"company": company, "grade": grade, "cert_number": None} if grade else None,
            "quantity": qty, "stack_key": f"k{grade}{company}{qty}", "created_at": datetime.now(UTC)}


def pt(source, grade, cents, kind="market", cur="USD", variant=None):
    return {"source": source, "kind": kind, "grade_key": grade, "variant": variant, "currency": cur,
            "market": cents, "as_of": None}


async def card(db, *points):
    """Catalog card (cardmarket 180.00 EUR raw, tcgplayer 250.10 USD) + scraped points."""
    rates = await get_rates(db)
    doc = make_card("a", "1")
    await db.cards.insert_one(doc)
    await store_card_prices(db, doc, rates)
    if points:
        await store_scraped_points(db, CID, list(points))


async def sale(db, grade, cents, days_ago=1, source="altxyz", cur="USD"):
    await db.sales.insert_one({"card_id": CID, "source": source, "grade_key": grade, "price": cents,
                               "currency": cur, "sold_at": datetime.now(UTC) - timedelta(days=days_ago),
                               "listing_id": uuid.uuid4().hex})


async def value(db, it):
    r = await db.collection_items.insert_one(it)
    [v] = await coll.valuate(db, {"_id": r.inserted_id})
    return v


async def test_graded_uses_exact_grade_price_not_raw(db):
    await card(db, pt("pricecharting", "PSA9", 4750, "sold"), pt("altxyz", "PSA9", 5400, "market"))
    v = await value(db, item(9))
    # preferred order: altxyz before pricecharting; USD 54.00 * 0.9
    assert (v["value"], v["match"], v["grade_key_used"], v["estimated"]) == (4860, "exact", "PSA9", False)
    assert v["value"] != 18000


async def test_three_sales_in_window_beat_market(db):
    await card(db, pt("altxyz", "PSA9", 9999, "market"))
    for c in (4000, 5000, 6000):
        await sale(db, "PSA9", c)
    v = await value(db, item(9))
    assert (v["price_kind"], v["value"], v["thin"], v["sample_size"]) == ("sold", 4500, False, 3)  # median 5000 USD


async def test_two_sales_do_not_beat_market_and_old_sales_ignored(db):
    await card(db, pt("altxyz", "PSA9", 10000, "market"))
    await sale(db, "PSA9", 1000)
    await sale(db, "PSA9", 2000)
    await sale(db, "PSA9", 3000, days_ago=200)  # outside the 90 d window
    v = await value(db, item(9))
    assert (v["price_kind"], v["value"], v["match"]) == ("market", 9000, "exact")


async def test_thin_sold_is_flagged_not_estimated_exact(db):
    await card(db)
    await sale(db, "PSA9", 5000)
    await sale(db, "PSA9", 7000)
    v = await value(db, item(9))
    assert (v["price_kind"], v["thin"], v["sample_size"], v["match"]) == ("sold", True, 2, "exact")
    assert v["value"] == 5400


async def test_bucket_fallback_is_estimated(db):
    await card(db, pt("pricecharting", "G9", 4331))
    v = await value(db, item(9))
    assert (v["match"], v["grade_key_used"], v["estimated"]) == ("bucket", "G9", True)


async def test_lower_grade_fallback_is_estimated(db):
    await card(db, pt("pricecharting", "PSA8", 2950, "sold"), pt("pricecharting", "PSA7", 1000, "sold"))
    v = await value(db, item(9))
    assert (v["match"], v["grade_key_used"], v["estimated"]) == ("lower", "PSA8", True)
    other = await value(db, item(9, company="BGS"))
    assert other["match"] == "raw_fallback"


async def test_raw_fallback_is_estimated_and_ignores_raw_sales(db):
    await card(db)
    for c in (100, 200, 300):
        await sale(db, "raw", c, source="pricecharting")
    v = await value(db, item(9))
    assert (v["match"], v["grade_key_used"], v["estimated"], v["value"]) == ("raw_fallback", "raw", True, 22509)  # tcgplayer 250.10 USD before catalog cardmarket


async def test_raw_item_uses_raw_price_exact_and_skips_scraped_raw_sales(db):
    await card(db)
    for c in (100, 200, 300):
        await sale(db, "raw", c, source="pricecharting")
    v = await value(db, item())
    assert (v["value"], v["match"], v["estimated"], v["source"]) == (22509, "exact", False, "tcgplayer")


async def test_unpriced_is_none_never_zero(db):
    await db.cards.insert_one(make_card("a", "1", priced=False))
    v = await value(db, item(9))
    assert v["value"] is None and v["match"] == "none" and v["estimated"] is False
    assert all(x is None for x in v["values"].values())


async def test_ask_never_used(db):
    await card(db, pt("cardmarket_web", "PSA9", 7777, "ask"))
    v = await value(db, item(9))
    assert v["match"] == "raw_fallback"


async def test_quantity_multiplies(db):
    await card(db, pt("altxyz", "PSA9", 5000, "market"))
    v = await value(db, item(9, qty=3))
    assert v["value"] == 13500


async def test_per_source_values_and_missing_variant_flagged(db):
    await card(db, pt("altxyz", "PSA9", 5000, "market"), pt("pricecharting", "PSA9", 4000, "market"))
    v = await value(db, item(9, variant="reverse"))
    assert v["values"]["altxyz"] == 4500 and v["values"]["pricecharting"] == 3600
    assert v["sources"]["altxyz"]["match"] == "exact"
    assert v["values"]["tcgplayer"] is not None  # no graded tcgplayer price -> its own raw fallback
    assert v["sources"]["tcgplayer"]["match"] == "raw_fallback"


async def test_snapshot_matches_valuate(db):
    await card(db, pt("altxyz", "PSA9", 5000, "market"))
    await db.collection_items.insert_one(item(9))
    await db.collection_items.insert_one(item(None, qty=2))
    vals = await coll.valuate(db)
    snap = await take_snapshot(db)
    assert snap["total_value"] == sum(v["value"] for v in vals) == 4500 + 2 * 22509
    assert snap["value_kind_breakdown"] == {"market": 4500 + 2 * 22509}
    assert snap["estimated_count"] == 0
    assert snap["totals_by_source"]["altxyz"] == 4500  # only the slab has an altxyz price
    assert snap["unpriced_count"]["altxyz"] == 1


async def test_stale_catalog_price_loses_to_fresh_source(db):
    old = datetime.now(UTC) - timedelta(days=400)
    await card(db, {**pt("cardmarket_web", "raw", 3000, cur="EUR"), "as_of": None})
    await db.cards.update_one({"_id": CID}, {"$set": {"latest_price.cardmarket.market.raw._.as_of": old,
                                                       "latest_price.tcgplayer.market": {}}})
    v = await value(db, item())
    assert (v["source"], v["value"]) == ("cardmarket_web", 3000)


async def test_stale_price_used_when_it_is_the_only_one(db):
    old = datetime.now(UTC) - timedelta(days=400)
    await card(db)
    await db.cards.update_one({"_id": CID}, {"$set": {"latest_price.cardmarket.market.raw._.as_of": old},
                                             "$unset": {"latest_price.tcgplayer": ""}})
    v = await value(db, item())
    assert (v["source"], v["value"]) == ("cardmarket", 18000)


async def test_preferred_order_scraped_before_catalog_cardmarket(db):
    await card(db, pt("pricecharting", "raw", 2567))
    v = await value(db, item())
    assert (v["source"], v["value"]) == ("pricecharting", 2310)  # 25.67 USD * 0.9


async def test_per_source_entries_carry_thin_and_sample_size(db):
    await card(db)
    await sale(db, "PSA9", 5000)
    v = await value(db, item(9))
    assert v["sources"]["altxyz"]["thin"] is True and v["sources"]["altxyz"]["sample_size"] == 1


async def test_snapshot_marks_weak_sources(db):
    await card(db, pt("pricecharting", "PSA9", 4750))
    await db.collection_items.insert_one(item(9))
    snap = await take_snapshot(db)
    assert snap["weak_by_source"]["pricecharting"] is False
    assert snap["weak_by_source"]["tcgplayer"] is True  # raw fallback
