import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, alerts, cards, collection, dashboard
from app.config import settings
from app.db.mongo import get_db, init_indexes
from app.jobs.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_indexes()
    sched = await start_scheduler()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="my-own-collection", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    return resp


for r in (cards.router, collection.router, dashboard.router, alerts.router, admin.router):
    app.include_router(r)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/ready")
async def ready():
    try:
        await get_db().command("ping")
    except Exception:
        raise HTTPException(503, "mongo unavailable")
    return {"status": "ready"}
