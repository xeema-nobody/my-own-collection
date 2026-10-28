from app.db import mongo


async def test_unused_text_index_is_dropped_and_not_recreated(db):
    await db.cards.create_index([("name", "text"), ("search_text", "text")], name="cards_text")
    assert "cards_text" in await db.cards.index_information()
    await mongo.init_indexes()
    assert "cards_text" not in await db.cards.index_information()
    await mongo.init_indexes()  # idempotent when already gone
    assert "name_norm_1" in await db.cards.index_information()
