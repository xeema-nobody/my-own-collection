from typing import Annotated

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from fetcher.service import FetchRejected, FetchResult, FetchService


class FetchIn(BaseModel):
    url: str
    wait_selector: str | None = None
    click_text: str | None = Field(None, max_length=100)
    click_labels: list[Annotated[str, Field(max_length=100)]] = Field(default_factory=list, max_length=10)
    wait_ms: int = Field(0, ge=0, le=30000)
    timeout_s: float | None = Field(None, gt=0, le=120)
    unattended: bool = False   # scheduled run: never wait for a human to log in


def build_app(service: FetchService, lifespan=None) -> FastAPI:
    app = FastAPI(title="moc-fetcher", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/status")
    async def status():
        return service.status()

    @app.post("/fetch/{site}", response_model=FetchResult)
    async def fetch(site: str, body: FetchIn):
        try:
            return await service.fetch(site, body.url, body.wait_selector,
                                       body.wait_ms, body.timeout_s, body.click_text,
                                       body.unattended, body.click_labels)
        except FetchRejected as e:
            raise HTTPException(422, str(e))

    @app.post("/close")
    async def close():
        await service.close()
        return {"ok": True}

    return app
