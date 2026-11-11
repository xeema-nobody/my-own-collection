from fastapi import APIRouter

from app.api.deps import get_db
from app.db.models import RepriceConfirmIn
from app.services import reprice as svc

router = APIRouter(prefix="/api/reprice", tags=["reprice"])


@router.get("")
async def table():
    """Listed stacks with market vs asking and the suggested price (market + markup)."""
    return await svc.table(get_db())


@router.post("/confirm")
async def confirm(body: RepriceConfirmIn):
    """The user's confirmation: saves the asking price in the app only and flags the listing for a platform update."""
    return await svc.confirm(get_db(), body)


@router.post("/evaluate")
async def evaluate():
    return await svc.evaluate(get_db())
