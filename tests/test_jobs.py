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


async def test_trigger_recorded_and_skipped_does_not_block(db):
    j = await jobs.start(db, "price_fetch")
    assert (await db.jobs.find_one({"_id": j}))["trigger"] == "manual"
    await jobs.finish(db, j, "ok")
    await jobs.record_skipped(db, "price_fetch", "scheduler", "fetcher down")
    await jobs.record_skipped(db, "price_fetch", "scheduler", "fetcher down")   # repeatable
    k = await jobs.start(db, "price_fetch", "scheduler")
    assert (await db.jobs.find_one({"_id": k}))["trigger"] == "scheduler"


async def test_last_success_ignores_error_and_skipped(db):
    assert await jobs.last_success(db, "price_fetch") is None
    await jobs.record_skipped(db, "price_fetch", "scheduler", "x")
    await jobs.finish(db, await jobs.start(db, "price_fetch"), "error")
    assert await jobs.last_success(db, "price_fetch") is None
    await jobs.finish(db, await jobs.start(db, "price_fetch"), "partial")
    assert await jobs.last_success(db, "price_fetch") is not None
