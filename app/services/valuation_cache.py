"""In-process cache of the whole-collection valuation.

`collection.valuate(db)` (no filter, no `as_of`) joins every stack with its card, sales and FX: ~560 ms at
5,000 stacks. The list/summary/dashboard endpoints all need it, so it is computed once and reused until
something that feeds it changes. Every write path calls `bump()`; `valuation_cache_ttl` bounds staleness
if one is ever missed (also covers time-dependent fields such as `stale`). Rows are shared: callers
must treat them as read-only. Single uvicorn process only (see docs/architecture.md)."""
import asyncio
import time

from app.config import settings

_rows: list[dict] | None = None
_db_name = ""
_built_at = 0.0
_version = 0          # bumped by writers; a build started before a bump is not stored
_lock: asyncio.Lock | None = None


def bump() -> None:
    """Drop the cached valuation (call after any change to stacks, prices, sales, FX or cards)."""
    global _rows, _version
    _rows = None
    _version += 1


_cur = ""


def _fresh() -> bool:
    ttl = settings.valuation_cache_ttl
    return _rows is not None and ttl > 0 and _db_name == _cur and time.monotonic() - _built_at < ttl


async def get_rows(db, build) -> list[dict]:
    """Cached rows, or `await build(db)` once (concurrent cold callers share one build)."""
    global _rows, _built_at, _lock, _db_name, _cur
    _cur = db.name
    if _fresh():
        return _rows  # type: ignore[return-value]
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if _fresh():
            return _rows  # type: ignore[return-value]
        started = _version
        rows = await build(db)
        if started == _version and settings.valuation_cache_ttl > 0:  # no write landed meanwhile
            _rows, _built_at, _db_name = rows, time.monotonic(), db.name
        return rows
