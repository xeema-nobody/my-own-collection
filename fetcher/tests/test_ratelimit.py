import asyncio

from fetcher.ratelimit import SiteLimiter
from tests.conftest import Clock


async def test_min_interval_between_starts():
    c = Clock()
    lim = SiteLimiter(3.0, jitter_s=0, clock=c, sleep=c.sleep)
    starts = []
    for _ in range(3):
        async with lim:
            starts.append(c.t)
    assert starts == [0.0, 3.0, 6.0]


async def test_concurrency_one():
    lim = SiteLimiter(0, jitter_s=0)
    active, peak = 0, 0

    async def job():
        nonlocal active, peak
        async with lim:
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(*(job() for _ in range(4)))
    assert peak == 1
