"""Image backfill off images.pokemontcg.io: reversible, idempotent, no network (fake provider)."""
import pytest

from app.services import catalog_images

OLD = "https://images.pokemontcg.io/sv3pt5/{n}.png"
NEW = "https://assets.tcgdex.net/en/sv/sv03.5/{n:03d}/low.webp"


def card(n, host_old=True, lang="en", set_id="sv3pt5"):
    img = {"small": OLD.format(n=n), "large": OLD.format(n=n)} if host_old else {"small": f"https://other/{n}.png", "large": "x"}
    return {"_id": f"pokemon:{set_id}-{n}", "tcg": "pokemon", "language": lang, "number": str(n), "set": {"id": set_id}, "images": img}


class Fake:
    def __init__(self, by_set, fail=()):
        self.by_set, self.fail = by_set, set(fail)

    async def set_images(self, sid):
        if sid in self.fail:
            raise RuntimeError("boom")
        return self.by_set.get(sid, {})


def up(*numbers):
    return {str(n): {"small": NEW.format(n=n), "large": NEW.format(n=n).replace("low", "high")} for n in numbers}


async def seed(db):
    await db.cards.insert_many([card(1), card(2), card(3, host_old=False), card(4, lang="ja"), card(9, set_id="zz")])


async def test_repoints_only_legacy_english_cards_and_keeps_old(db):
    await seed(db)
    stats = await catalog_images.repoint_images(Fake({"sv3pt5": up(1, 3, 4)}))
    one = await db.cards.find_one({"_id": "pokemon:sv3pt5-1"})
    assert one["images"]["small"] == NEW.format(n=1) and one["images_legacy"]["small"] == OLD.format(n=1)
    assert (await db.cards.find_one({"_id": "pokemon:sv3pt5-2"}))["images"]["small"] == OLD.format(n=2)  # no TCGdex art: kept
    assert "images_legacy" not in await db.cards.find_one({"_id": "pokemon:sv3pt5-3"})                   # other host: untouched
    assert "images_legacy" not in await db.cards.find_one({"_id": "pokemon:sv3pt5-4"})
    assert stats["repointed"] == 1 and stats["no_image"] == 2 and stats["no_counterpart"] == ["zz"]
    job = await db.jobs.find_one({"type": "catalog_images"})
    assert job["status"] == "ok"


async def test_idempotent_and_legacy_saved_once(db):
    await seed(db)
    await catalog_images.repoint_images(Fake({"sv3pt5": up(1)}))
    again = await catalog_images.repoint_images(Fake({"sv3pt5": up(1)}))
    assert again["repointed"] == 0
    assert (await db.cards.find_one({"_id": "pokemon:sv3pt5-1"}))["images_legacy"]["small"] == OLD.format(n=1)


async def test_failed_set_is_reported_and_rest_go_through(db):
    await seed(db)
    stats = await catalog_images.repoint_images(Fake({"sv3pt5": up(1)}, fail=["zz"]))
    assert stats["failed_sets"] == ["zz"] and stats["repointed"] == 1
    assert (await db.jobs.find_one({"type": "catalog_images"}))["status"] == "partial"


async def test_status_and_restore_round_trip(db):
    await seed(db)
    assert (await catalog_images.status(db))["legacy"] == 3          # cards 1, 2 and zz-9
    await catalog_images.repoint_images(Fake({"sv3pt5": up(1, 2)}))
    st = await catalog_images.status(db)
    assert st["legacy"] == 1 and st["restorable"] == 2
    assert await catalog_images.restore_images(db) == 2
    one = await db.cards.find_one({"_id": "pokemon:sv3pt5-1"})
    assert one["images"]["small"] == OLD.format(n=1) and "images_legacy" not in one


async def test_provider_without_image_listing_is_refused(db):
    with pytest.raises(ValueError):
        await catalog_images.repoint_images(object())
