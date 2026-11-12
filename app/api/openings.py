from fastapi import APIRouter, Query

from app.api.deps import get_db, spawn
from app.db.models import PullsIn
from app.services import openings as svc
from app.services.refresh import price_new_tracked

router = APIRouter(prefix="/api/openings", tags=["openings"])


@router.get("")
async def list_openings(limit: int = Query(100, ge=1, le=300)):
    return await svc.list_openings(get_db(), limit)


@router.get("/report")
async def report():
    return await svc.report(get_db())


@router.get("/{opening_id}")
async def get_opening(opening_id: str):
    return await svc.get(get_db(), opening_id)


@router.post("/{opening_id}/pulls", status_code=201)
async def add_pulls(opening_id: str, body: PullsIn):
    out = await svc.add_pulls(get_db(), opening_id, body.pulled)
    for cid in {p["card_id"] for p in out["pulled"]}:
        spawn(price_new_tracked(cid))
    return out
