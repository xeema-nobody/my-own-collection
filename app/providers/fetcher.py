"""Client for the host-Mac browser fetcher (fetcher/). Only place that calls it."""
from dataclasses import dataclass

import httpx

from app.config import settings

LOGIN_WAIT_S = 330   # fetcher waits up to LOGIN_TIMEOUT_S (300) + grace for the user to log in


class FetcherUnavailable(RuntimeError):
    """Fetcher not running / unreachable / bad reply."""


@dataclass
class FetchResponse:
    status: str                 # ok | login_timeout | blocked | error
    final_url: str | None = None
    title: str | None = None
    html: str | None = None
    detail: str | None = None


class FetcherClient:
    def __init__(self, base_url: str | None = None, transport: httpx.AsyncBaseTransport | None = None,
                 unattended: bool = False):
        self.base_url = (base_url or settings.fetcher_url).rstrip("/")
        self.unattended = unattended
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=timeout, transport=self._transport)

    async def fetch(self, site: str, url: str, wait_selector: str | None = None, wait_ms: int = 0,
                    click_text: str | None = None) -> FetchResponse:
        body = {"url": url, "wait_selector": wait_selector, "wait_ms": wait_ms,
                "click_text": click_text, "unattended": self.unattended}
        try:
            async with self._client(LOGIN_WAIT_S) as c:
                r = await c.post(f"/fetch/{site}", json=body)
        except httpx.HTTPError as e:
            raise FetcherUnavailable(f"fetcher unreachable at {self.base_url}: {e}") from e
        if r.status_code != 200:
            raise FetcherUnavailable(f"fetcher HTTP {r.status_code}: {r.text[:200]}")
        d = r.json()
        return FetchResponse(d["status"], d.get("final_url"), d.get("title"), d.get("html"),
                             d.get("detail"))

    async def status(self) -> dict:
        try:
            async with self._client(5) as c:
                r = await c.get("/status")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise FetcherUnavailable(f"fetcher unreachable at {self.base_url}: {e}") from e
