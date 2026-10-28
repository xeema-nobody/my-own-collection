from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError


class JobRunning(Exception):
    """A job of this type is already running (one at a time per type)."""


async def is_running(db, type_: str) -> bool:
    return await db.jobs.find_one({"type": type_, "status": "running"}, {"_id": 1}) is not None


async def start(db, type_: str, trigger: str = "manual") -> object:
    # The partial unique index on (type, status=running) makes this check atomic.
    try:
        r = await db.jobs.insert_one({"type": type_, "started_at": datetime.now(timezone.utc),
                                      "status": "running", "stats": {}, "trigger": trigger})
    except DuplicateKeyError:
        raise JobRunning(f"{type_} already running") from None
    return r.inserted_id


async def mark_orphans(db) -> int:
    """Jobs left `running` by a crashed/restarted process would block their type forever."""
    r = await db.jobs.update_many({"status": "running"}, {"$set": {
        "status": "interrupted", "finished_at": datetime.now(timezone.utc)}})
    return r.modified_count


async def finish(db, job_id, status: str, stats: dict | None = None, error: str | None = None):
    await db.jobs.update_one({"_id": job_id}, {"$set": {
        "status": status, "finished_at": datetime.now(timezone.utc),
        "stats": stats or {}, "error": error}})


async def progress(db, job_id, stats: dict):
    await db.jobs.update_one({"_id": job_id}, {"$set": {"stats": stats}})


async def record_skipped(db, type_: str, trigger: str, reason: str):
    """A scheduled run that could not start; visible in the jobs log, never blocks the type."""
    now = datetime.now(timezone.utc)
    await db.jobs.insert_one({"type": type_, "started_at": now, "finished_at": now, "status": "skipped",
                              "stats": {}, "trigger": trigger, "error": reason})


async def last_success(db, type_: str) -> datetime | None:
    """Finish time of the latest ok/partial run of this type (any trigger)."""
    d = await db.jobs.find_one({"type": type_, "status": {"$in": ["ok", "partial"]}}, sort=[("finished_at", -1)])
    return d["finished_at"] if d else None
