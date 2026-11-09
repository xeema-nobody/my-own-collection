from fastapi import APIRouter

from app.api.deps import get_db, spawn
from app.db.models import BulkIdsIn, WishIn, WishPatch
from app.services import wishlist as svc
from app.services.price_fetch import wishlist_freshness
from app.services.refresh import price_new_tracked

router = APIRouter(prefix="/api/wishlist", tags=["wishlist"])


@router.get("")
async def list_wishlist(card_id: str | None = None):
    return await svc.list_(get_db(), card_id)


@router.get("/prices")
async def wishlist_prices():
    """Price freshness of the wishlisted cards (fresh / stale / never fetched)."""
    return await wishlist_freshness(get_db())


@router.post("", status_code=201)
async def add_wish(body: WishIn):
    out = await svc.add(get_db(), body)
    spawn(price_new_tracked(body.card_id))
    return out


@router.post("/bulk-remove")
async def bulk_remove(body: BulkIdsIn):
    return await svc.remove_many(get_db(), body.ids)


@router.patch("/{wish_id}")
async def patch_wish(wish_id: str, body: WishPatch):
    return await svc.patch(get_db(), wish_id, body)


@router.delete("/{wish_id}", status_code=204)
async def remove_wish(wish_id: str):
    await svc.remove(get_db(), wish_id)
