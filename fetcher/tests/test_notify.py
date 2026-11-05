import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from fetcher.config import Settings
from fetcher.notify import Notifier, applescript, event_text, start_notifier

NOW = datetime.now(timezone.utc)


def ev(i, name="Mew", rule="Stack Mew #25 above 1", mins=1, type_="alert"):
    return {"id": i, "type": type_, "name": name, "rule": rule,
            "fired_at": (NOW + timedelta(minutes=mins)).isoformat(), "read": False}


class Rig:
    def __init__(self, tmp_path, events=None, enabled=True):
        self.cfg = Settings(notify_state=tmp_path / "notified.json", notify_enabled=enabled)
        self.events = list(events or [])
        self.shown: list[tuple[str, str]] = []
        self.app_down = False
        self.show_fails = False

    async def fetch(self):
        if self.app_down:
            raise ConnectionError("app down")
        return list(self.events)

    async def show(self, title, body):
        if self.show_fails:
            raise RuntimeError("osascript failed")
        self.shown.append((title, body))

    def notifier(self):
        return Notifier(self.cfg, fetch_events=self.fetch, show=self.show)


async def test_first_run_seeds_without_notifying_backlog(tmp_path):
    r = Rig(tmp_path, [ev("a", mins=-30), ev("b", mins=-20)])
    await r.notifier().tick()
    assert r.shown == []
    assert r.cfg.notify_state.exists()


async def test_new_event_notifies_once(tmp_path):
    r = Rig(tmp_path)
    n = r.notifier()
    await n.tick()                      # seed
    r.events = [ev("a")]
    await n.tick()
    await n.tick()                      # same event next tick
    assert r.shown == [("my-own-collection", "Mew: Stack Mew #25 above 1")]


async def test_several_events_one_summary(tmp_path):
    r = Rig(tmp_path)
    n = r.notifier()
    await n.tick()
    r.events = [ev("a"), ev("b", mins=2), ev("c", mins=3)]
    await n.tick()
    assert [b for _, b in r.shown] == ["3 new price alerts"]


async def test_restart_does_not_repeat(tmp_path):
    r = Rig(tmp_path)
    await r.notifier().tick()
    r.events = [ev("a")]
    await r.notifier().tick()
    assert len(r.shown) == 1
    await r.notifier().tick()           # fresh Notifier, same state file
    assert len(r.shown) == 1


async def test_event_read_in_ui_still_counts_as_notified(tmp_path):
    r = Rig(tmp_path)
    n = r.notifier()
    await n.tick()
    r.events = [ev("a")]
    await n.tick()
    r.events = []                       # marked read in the UI -> gone from unread list
    await n.tick()
    r.events = [ev("a")]                # and back (e.g. unread again): not re-notified
    await n.tick()
    assert len(r.shown) == 1


async def test_app_down_does_not_raise_or_change_state(tmp_path):
    r = Rig(tmp_path)
    n = r.notifier()
    await n.tick()
    before = r.cfg.notify_state.read_text()
    r.app_down = True
    await n.tick()
    assert r.cfg.notify_state.read_text() == before
    r.app_down = False
    r.events = [ev("a")]
    await n.tick()                      # recovers
    assert len(r.shown) == 1


async def test_app_down_on_first_run_leaves_no_state(tmp_path):
    r = Rig(tmp_path)
    r.app_down = True
    await r.notifier().tick()
    assert not r.cfg.notify_state.exists()


async def test_show_failure_retries_next_tick(tmp_path):
    r = Rig(tmp_path)
    n = r.notifier()
    await n.tick()
    r.events = [ev("a")]
    r.show_fails = True
    await n.tick()
    assert r.shown == []
    r.show_fails = False
    await n.tick()
    assert len(r.shown) == 1


async def test_old_event_not_in_seed_is_ignored(tmp_path):
    """fired before the high-water mark and not seeded (e.g. unread backlog beyond fetch limit)."""
    r = Rig(tmp_path)
    n = r.notifier()
    await n.tick()
    r.events = [ev("old", mins=-60)]
    await n.tick()
    assert r.shown == []


async def test_corrupt_state_reseeds(tmp_path):
    r = Rig(tmp_path, [ev("a", mins=-5)])
    r.cfg.notify_state.write_text("{not json")
    await r.notifier().tick()
    assert r.shown == []
    assert json.loads(r.cfg.notify_state.read_text())["ids"] == ["a"]


def test_event_text_alert_and_system():
    assert event_text({"type": "alert", "name": "Mew", "rule": "r"}) == "Mew: r"
    assert event_text({"type": "system", "name": None, "rule": "Price fetch failed"}) == "Price fetch failed"
    assert event_text({"type": "alert", "name": None, "rule": "r"}) == "r"


def test_applescript_escapes_quotes_backslashes_newlines():
    s = applescript('Mew "ex"\\x\nline2', 'ti"tle')
    assert s == 'display notification "Mew \\"ex\\"\\\\x line2" with title "ti\\"tle"'


async def test_disabled_flag_starts_no_task(tmp_path):
    r = Rig(tmp_path, enabled=False)
    assert start_notifier(r.cfg) is None


async def test_enabled_flag_starts_cancellable_task(tmp_path):
    r = Rig(tmp_path, enabled=True)
    r.cfg.notify_poll_s = 3600
    task = start_notifier(r.cfg, fetch_events=r.fetch, show=r.show)
    assert isinstance(task, asyncio.Task)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
