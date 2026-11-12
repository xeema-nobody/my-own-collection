import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import admin, alerts, cards, collection, dashboard, openings, photos, sealed, publish, reprice, scan, wishlist
from app.config import settings
from app.db.mongo import get_db, init_indexes
from app.jobs.scheduler import start_scheduler
from app.security import gate

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_indexes()
    sched = await start_scheduler()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="my-own-collection", lifespan=lifespan)
allowed_origins = {o.strip() for o in f"{settings.cors_origins},{settings.extension_origins}".split(",") if o.strip()}
app.add_middleware(CORSMiddleware, allow_origins=sorted(allowed_origins),
                   allow_methods=["*"], allow_headers=["*"])
# DNS rebinding: a rebound hostname would make the API same-origin for an attacker page
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[h.strip() for h in settings.allowed_hosts.split(",")])


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def origin_guard(request, call_next):
    """CSRF: a web page the user visits could POST to localhost (e.g. text/plain to the raw-body import).
    Browsers always send Origin on cross-site writes; curl/scripts send none and pass."""
    origin = request.headers.get("origin")
    # phone mode (set by the gate): only the tailnet origin counts, the laptop origin does not
    ok = {settings.lan_origin} if getattr(request.state, "phone", False) else allowed_origins
    if request.method not in SAFE_METHODS and origin and origin not in ok:
        return JSONResponse({"detail": "origin not allowed"}, status_code=403)
    return await call_next(request)


app.middleware("http")(gate)  # phone mode allowlist; registered after origin_guard so it runs first


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    return resp


for r in (cards.router, collection.router, dashboard.router, wishlist.router, alerts.router, admin.router, scan.router, photos.router, publish.router, reprice.router, sealed.router, openings.router):
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
