import asyncio
import logging

from fastapi import HTTPException

from app.db.mongo import get_db  # noqa: F401  (re-export: routers import db accessor from here)
from app.services import jobs as jobs_svc

log = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()


def spawn(coro):
    # Keep a ref so the task isn't GC'd; state lives in the `jobs` collection.
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(lambda t: (_tasks.discard(t), t.exception() and log.error("job failed: %s", t.exception())))


async def ensure_idle(type_: str):
    # Fast 409; the unique partial index on `jobs` is the race-free backstop.
    if await jobs_svc.is_running(get_db(), type_):
        raise HTTPException(409, f"{type_} already running")


def clean(d: dict | None) -> dict | None:
    if d is None:
        return None
    d = {k: v for k, v in d.items() if k not in ("search_text", "name_norm", "number_sort")}
    d["id"] = d.pop("_id")
    return d
