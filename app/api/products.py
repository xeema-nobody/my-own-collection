from fastapi import APIRouter

from app.api.deps import get_db
from app.db.models import ProductIn, ProductPatch
from app.services import products as svc

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("")
async def list_products(status: str | None = None, type: str | None = None):
    return await svc.list_(get_db(), status, type)


@router.get("/summary")
async def summary():
    return await svc.summary(get_db())


@router.post("", status_code=201)
async def add_product(body: ProductIn):
    return await svc.create(get_db(), body)


@router.patch("/{product_id}")
async def patch_product(product_id: str, body: ProductPatch):
    return await svc.patch(get_db(), product_id, body)


@router.delete("/{product_id}", status_code=204)
async def remove_product(product_id: str):
    await svc.remove(get_db(), product_id)
