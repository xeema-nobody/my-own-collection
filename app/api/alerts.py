from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import get_db
from app.db.models import AlertIn, AlertPatch
from app.services import alerts as svc

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class ReadIn(BaseModel):
    ids: list[str] | None = None   # None = all


@router.get("")
async def list_rules():
    return await svc.list_rules(get_db())


@router.post("", status_code=201)
async def create_rule(body: AlertIn):
    return await svc.create(get_db(), body)


@router.get("/events")
async def list_events(unread: bool = False, limit: int = Query(100, ge=1, le=500)):
    return await svc.events(get_db(), unread, limit)


@router.post("/events/read")
async def read_events(body: ReadIn):
    return {"marked": await svc.mark_read(get_db(), body.ids)}


@router.get("/unread-count")
async def unread_count():
    return {"count": await svc.unread_count(get_db())}


@router.post("/evaluate")
async def evaluate_now():
    return {"fired": await svc.evaluate(get_db())}


@router.patch("/{alert_id}")
async def patch_rule(alert_id: str, body: AlertPatch):
    return await svc.patch(get_db(), alert_id, body)


@router.delete("/{alert_id}", status_code=204)
async def delete_rule(alert_id: str):
    await svc.delete(get_db(), alert_id)
