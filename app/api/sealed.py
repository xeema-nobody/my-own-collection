from fastapi import APIRouter, Query

from app.api.deps import get_db
from app.db.models import SealedIn
from app.services import sealed as svc

router = APIRouter(prefix="/api/sealed", tags=["sealed"])


@router.get("/types")
async def types():
    return [{"value": k, "label": v} for k, v in svc.TYPES.items()]


@router.get("")
async def entries(q: str | None = None, set: str | None = None, limit: int = Query(100, ge=1, le=300)):
    """Sealed catalog entries added so far."""
    return await svc.list_entries(get_db(), q, set, limit)


@router.post("", status_code=201)
async def add_sealed(body: SealedIn):
    """Define-or-find the product from a set + type, then add one stack to the collection."""
    return await svc.add(get_db(), body)
