import asyncio
import random
import time
from collections.abc import Awaitable, Callable


class SiteLimiter:
    """Concurrency 1 plus a minimum gap between request starts for one site."""

    def __init__(self, min_interval_s: float, jitter_s: float = 1.0,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.min_interval_s, self.jitter_s = min_interval_s, jitter_s
        self._clock, self._sleep = clock, sleep
        self._lock = asyncio.Lock()
        self._last_start: float | None = None

    async def __aenter__(self):
        await self._lock.acquire()
        if self._last_start is not None:
            gap = self.min_interval_s + random.uniform(0, self.jitter_s)
            wait = self._last_start + gap - self._clock()
            if wait > 0:
                await self._sleep(wait)
        self._last_start = self._clock()
        return self

    async def __aexit__(self, *exc):
        self._lock.release()
