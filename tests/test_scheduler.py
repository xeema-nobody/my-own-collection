from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.jobs import scheduler as sch
from app.providers.fetcher import FetcherUnavailable
from app.services import jobs
from tests.conftest import make_card

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


async def done(db, type_, finished):
    r = await db.jobs.insert_one({"type": type_, "status": "ok", "started_at": finished, "finished_at": finished,
                                  "stats": {}, "trigger": "manual"})
    return r.inserted_id


def recorder(calls, boom=()):
    def mk(name):
        async def run(trigger):
            calls.append((name, trigger))
            if name in boom:
                raise RuntimeError("boom")
        return run
    return {n: mk(n) for n in sch.TASKS}


def test_build_scheduler_registers_all_tasks_with_configured_crons():
    s = sch.build_scheduler()
    got = {j.id: j.trigger for j in s.get_jobs()}
    assert list(got) == list(sch.TASKS)
    f = lambda name, field: str(next(x for x in got[name].fields if x.name == field))  # noqa: E731
    assert f("daily_refresh", "hour") == "4" and f("weekly_catalog", "day_of_week") == "0"
    assert all(j.max_instances == 1 and j.coalesce for j in s.get_jobs())


async def test_run_task_isolates_failures_and_busy():
    calls = []
    r = recorder(calls, boom={"daily_fetch"})
    assert await sch.run_task("daily_fetch", runners=r) is False     # exception swallowed

    async def busy(trigger):
        raise jobs.JobRunning("x")
    assert await sch.run_task("daily_fetch", runners={"daily_fetch": busy}) is False
    assert await sch.run_task("daily_snapshot", runners=r) is True
    assert calls == [("daily_fetch", "scheduler"), ("daily_snapshot", "scheduler")]


async def test_catch_up_runs_only_overdue_in_order(db):
    await db.sets.insert_one({"_id": "pokemon:x", "tcg": "pokemon", "external_id": "x"})
    await done(db, "price_refresh", NOW - timedelta(hours=2))
    await done(db, "price_fetch", NOW - timedelta(hours=30))
    await db.collection_snapshots.insert_one({"date": "d", "taken_at": NOW - timedelta(hours=25)})
    await done(db, "catalog_import", NOW - timedelta(days=3))
    calls = []
    ran = await sch.catch_up(db, lambda: NOW, recorder(calls))
    assert ran == ["daily_fetch", "daily_snapshot"]
    assert calls == [("daily_fetch", "catchup"), ("daily_snapshot", "catchup")]


async def test_catch_up_nothing_when_fresh_and_weekly_after_7d(db):
    await db.sets.insert_one({"_id": "pokemon:x", "tcg": "pokemon", "external_id": "x"})
    for t in ("price_refresh", "price_fetch"):
        await done(db, t, NOW - timedelta(hours=1))
    await db.collection_snapshots.insert_one({"date": "d", "taken_at": NOW - timedelta(hours=1)})
    await done(db, "catalog_import", NOW - timedelta(days=8))
    assert await sch.catch_up(db, lambda: NOW, recorder([])) == ["weekly_catalog"]


async def test_catch_up_skips_catalog_when_never_imported(db):
    assert "weekly_catalog" not in await sch.overdue(db, NOW)
    assert {"daily_refresh", "daily_fetch", "daily_snapshot"} <= set(await sch.overdue(db, NOW))


async def test_catch_up_continues_after_failure(db):
    calls = []
    await sch.catch_up(db, lambda: NOW, recorder(calls, boom={"daily_refresh"}))
    assert [c[0] for c in calls] == ["daily_refresh", "daily_fetch", "daily_snapshot"]


async def test_fetch_task_records_skipped_when_fetcher_down(db, monkeypatch):
    class Down:
        def __init__(self, *a, **k): pass
        async def status(self): raise FetcherUnavailable("down")
    monkeypatch.setattr(sch, "FetcherClient", Down)
    await sch._fetch("scheduler")
    j = await db.jobs.find_one({"type": "price_fetch"})
    assert j["status"] == "skipped" and j["trigger"] == "scheduler" and "down" in j["error"]


async def test_fetch_task_caps_and_passes_trigger(db, monkeypatch):
    for n in "123":
        await db.cards.insert_one(make_card("s", n))
        await db.collection_items.insert_one({"stack_key": n, "card_id": f"pokemon:s-{n}"})

    class Up:
        def __init__(self, *a, unattended=False, **k): assert unattended
        async def status(self): return {}
    seen = {}

    async def fake_fetch(cards, **kw):
        seen.update(cards=cards, **kw)
    monkeypatch.setattr(sch, "FetcherClient", Up)
    monkeypatch.setattr(sch, "fetch_prices", fake_fetch)
    monkeypatch.setattr(settings, "scheduler_fetch_cap", 2)
    await sch._fetch("scheduler")
    assert len(seen["cards"]) == 2 and seen["trigger"] == "scheduler"
