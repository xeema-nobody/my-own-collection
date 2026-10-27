from datetime import datetime, timezone


async def start(db, type_: str) -> object:
    r = await db.jobs.insert_one({"type": type_, "started_at": datetime.now(timezone.utc),
                                  "status": "running", "stats": {}})
    return r.inserted_id


async def finish(db, job_id, status: str, stats: dict | None = None, error: str | None = None):
    await db.jobs.update_one({"_id": job_id}, {"$set": {
        "status": status, "finished_at": datetime.now(timezone.utc),
        "stats": stats or {}, "error": error}})


async def progress(db, job_id, stats: dict):
    await db.jobs.update_one({"_id": job_id}, {"$set": {"stats": stats}})
