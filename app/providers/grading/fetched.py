"""Providers whose site blocks plain HTTP (Cloudflare): read only through the host fetcher (real Chrome).
We never defeat a wall: a blocked page degrades to link-only."""
from app.providers.fetcher import FetcherClient, FetcherUnavailable
from app.providers.grading.base import (
    BLOCKED, FOUND, NOT_FOUND, RESTART_HINT, UNAVAILABLE, CertInfo, clean_cert, now)


class FetchedProvider:
    grader = ""
    site = ""             # fetcher site id
    wait_selector = ""

    def __init__(self, client: FetcherClient | None = None):
        self.client = client or FetcherClient(unattended=True)

    def cert_url(self, cert: str) -> str:
        raise NotImplementedError

    def parse(self, html: str, cert: str) -> CertInfo:
        raise NotImplementedError

    def _fail(self, cert, status, detail) -> CertInfo:
        return CertInfo(self.grader, cert, status, self.cert_url(cert), detail=detail, fetched_at=now())

    async def lookup(self, cert: str) -> CertInfo:
        cert = clean_cert(cert) or ""
        try:
            sites = await self.client.sites()
        except FetcherUnavailable:
            return self._fail(cert, UNAVAILABLE, f"fetcher is not running: scripts/fetcher.sh start")
        if self.site not in sites:
            return self._fail(cert, UNAVAILABLE, f"fetcher has no '{self.site}' site; {RESTART_HINT}")
        try:
            r = await self.client.fetch(self.site, self.cert_url(cert), wait_selector=self.wait_selector)
        except FetcherUnavailable as e:
            return self._fail(cert, UNAVAILABLE, str(e))
        if r.status in ("blocked", "login_timeout"):
            return self._fail(cert, BLOCKED, f"{self.grader} page blocked the fetcher")
        if r.status != "ok" or not r.html:
            return self._fail(cert, UNAVAILABLE, r.detail or f"{self.grader} page not read")
        info = self.parse(r.html, cert)
        if info.status == NOT_FOUND and not info.detail:
            info.detail = f"{self.grader} has no such cert"
        return info


__all__ = ["FetchedProvider", "FOUND"]
