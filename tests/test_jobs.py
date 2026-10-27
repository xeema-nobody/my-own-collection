import pytest

from app.services import jobs


async def test_one_running_job_per_type(db):
    a = await jobs.start(db, "price_refresh")
    with pytest.raises(jobs.JobRunning):
        await jobs.start(db, "price_refresh")
    await jobs.start(db, "catalog_import")  # other type is independent
    assert await jobs.is_running(db, "price_refresh")
    await jobs.finish(db, a, "ok")
    assert not await jobs.is_running(db, "price_refresh")
    await jobs.start(db, "price_refresh")


async def test_mark_orphans_unblocks_type(db):
    await jobs.start(db, "price_refresh")
    assert await jobs.mark_orphans(db) == 1
    await jobs.start(db, "price_refresh")
