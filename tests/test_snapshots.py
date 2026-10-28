from app.services.snapshots import take_snapshot


async def test_snapshot_rerun_same_day_replaces_not_duplicates(db):
    await take_snapshot(db)
    await db.collection_items.insert_one({"stack_key": "k", "card_id": "pokemon:missing", "quantity": 2,
                                          "language": "en", "condition": "NM", "grading": None, "variant": None})
    again = await take_snapshot(db)
    assert await db.collection_snapshots.count_documents({}) == 1
    assert again["item_count"] == 1  # second run overwrote the first (empty) one
