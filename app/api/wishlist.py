from fastapi import APIRouter

from app.api.deps import get_db
from app.db.models import WishIn, WishPatch
from app.services import wishlist as svc

router = APIRouter(prefix="/api/wishlist", tags=["wishlist"])


@router.get("")
async def list_wishlist(card_id: str | None = None):
    return await svc.list_(get_db(), card_id)


@router.post("", status_code=201)
async def add_wish(body: WishIn):
    return await svc.add(get_db(), body)


@router.patch("/{wish_id}")
async def patch_wish(wish_id: str, body: WishPatch):
    return await svc.patch(get_db(), wish_id, body)


@router.delete("/{wish_id}", status_code=204)
async def remove_wish(wish_id: str):
    await svc.remove(get_db(), wish_id)
