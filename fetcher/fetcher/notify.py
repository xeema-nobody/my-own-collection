"""macOS notification for new alert events.

Polls the app's unread alert events and shows one notification for events not seen before.
Dedupe is a high-water mark + notified ids kept in `settings.notify_state`: the UI's `read`
flag is not used, so reading an alert in the UI neither hides nor repeats a notification.
First run (no state file) seeds the mark silently: the existing backlog is never announced.
"""
import asyncio
import json
import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import httpx

from fetcher.config import Settings

log = logging.getLogger("fetcher.notify")

TITLE = "my-own-collection"
MAX_IDS = 200

FetchEvents = Callable[[], Awaitable[list[dict]]]
Show = Callable[[str, str], Awaitable[None]]


def event_text(e: dict) -> str:
    rule = e.get("rule") or "price alert"
    name = e.get("name")
    return f"{name}: {rule}" if name and e.get("type") != "system" else rule


def applescript(body: str, title: str) -> str:
    def q(s: str) -> str:
        s = " ".join(s.split())          # newlines/tabs -> single spaces
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"display notification {q(body)} with title {q(title)}"


async def osascript_show(title: str, body: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", applescript(body, title),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode:
        raise RuntimeError(f"osascript exit {proc.returncode}: {err.decode(errors='replace').strip()}")


def _http_fetch(cfg: Settings) -> FetchEvents:
    async def fetch() -> list[dict]:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{cfg.app_url}/api/alerts/events", params={"unread": "true"})
            r.raise_for_status()
            return r.json()
    return fetch


def _ts(s: str) -> datetime:
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class Notifier:
    def __init__(self, cfg: Settings, fetch_events: FetchEvents | None = None, show: Show | None = None):
        self.cfg = cfg
        self.fetch_events = fetch_events or _http_fetch(cfg)
        self.show = show or osascript_show

    def _load(self) -> dict | None:
        try:
            st = json.loads(self.cfg.notify_state.read_text())
            return {"high_water": _ts(st["high_water"]), "ids": list(st["ids"])}
        except (OSError, ValueError, KeyError, TypeError):
            return None                  # missing or corrupt -> reseed silently

    def _save(self, high_water: datetime, ids: list[str]) -> None:
        path = self.cfg.notify_state
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".notified-")
        with os.fdopen(fd, "w") as f:
            json.dump({"high_water": high_water.isoformat(), "ids": ids[-MAX_IDS:]}, f)
        os.replace(tmp, path)

    async def tick(self) -> None:
        """One poll. Never raises: any failure leaves state untouched and is retried next tick."""
        try:
            events = await self.fetch_events()
            st = self._load()
            if st is None:
                self._save(datetime.now(timezone.utc), [e["id"] for e in events])
                return
            new = [e for e in events if e["id"] not in st["ids"] and _ts(e["fired_at"]) > st["high_water"]]
            if not new:
                return
            new.sort(key=lambda e: _ts(e["fired_at"]))
            body = event_text(new[0]) if len(new) == 1 else f"{len(new)} new price alerts"
            await self.show(TITLE, body)
            self._save(max(st["high_water"], _ts(new[-1]["fired_at"])), st["ids"] + [e["id"] for e in new])
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - app down, bad payload, osascript failure
            log.debug("notify tick failed: %s", e)

    async def run(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(self.cfg.notify_poll_s)


def start_notifier(cfg: Settings, fetch_events: FetchEvents | None = None,
                   show: Show | None = None) -> asyncio.Task | None:
    if not cfg.notify_enabled:
        return None
    return asyncio.create_task(Notifier(cfg, fetch_events, show).run())
