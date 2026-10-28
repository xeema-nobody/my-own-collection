import asyncio
from contextlib import asynccontextmanager

from fetcher.api import build_app
from fetcher.browser import ChromeCdpDriver
from fetcher.config import settings
from fetcher.service import FetchService

service = FetchService(settings, ChromeCdpDriver(settings))


@asynccontextmanager
async def lifespan(_):
    async def reaper():
        while True:
            await asyncio.sleep(10)
            await service.reap_idle()

    task = asyncio.create_task(reaper())
    yield
    task.cancel()
    await service.close()


app = build_app(service, lifespan)
