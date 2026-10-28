"""Fetch state machine: anonymous first, pause for the user on login/challenge, resume."""
import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from fetcher.browser import BrowserError, Driver, Page
from fetcher.config import Settings
from fetcher.ratelimit import SiteLimiter
from fetcher.sites import SITES, PageState, SiteConfig, is_challenge, needs_login


class FetchRejected(ValueError):
    """Bad site or URL outside the site's hosts."""


class FetchResult(BaseModel):
    status: Literal["ok", "login_timeout", "blocked", "error"]
    final_url: str | None = None
    title: str | None = None
    html: str | None = None
    detail: str | None = None


class FetchService:
    def __init__(self, cfg: Settings, driver: Driver,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 jitter_s: float = 1.0):
        self.cfg, self.driver, self._clock, self._sleep = cfg, driver, clock, sleep
        self._limiters = {s.id: SiteLimiter(s.min_interval_s, jitter_s, clock, sleep)
                          for s in SITES.values()}
        self.site_state: dict[str, str] = {s: "idle" for s in SITES}
        self._waited: set[str] = set()
        self.last_error: str | None = None
        self._active = 0
        self._last_used = clock()

    def status(self) -> dict:
        return {"browser": "up" if self.driver.is_up else "down",
                "sites": dict(self.site_state), "last_error": self.last_error}

    async def fetch(self, site_id: str, url: str, wait_selector: str | None = None,
                    wait_ms: int = 0, timeout_s: float | None = None,
                    click_text: str | None = None, unattended: bool = False) -> FetchResult:
        site = SITES.get(site_id)
        if site is None:
            raise FetchRejected(f"unknown site {site_id!r}")
        if not site.allows(url):
            raise FetchRejected(f"url not on {site_id} hosts")
        self._active += 1
        try:
            async with self._limiters[site_id]:
                return await self._run(site, url, wait_selector, wait_ms,
                                       timeout_s or self.cfg.nav_timeout_s, click_text, unattended)
        finally:
            self._active -= 1
            self.site_state[site_id] = "idle"
            self._last_used = self._clock()

    async def _state(self, page: Page) -> PageState:
        return PageState(await page.title(), await page.url(), await page.text())

    async def _run(self, site: SiteConfig, url, wait_selector, wait_ms, timeout_s,
                   click_text=None, unattended=False) -> FetchResult:
        self.site_state[site.id] = "fetching"
        page: Page | None = None
        try:
            page = await self.driver.new_page()
            await page.goto(url, timeout_s)
            blocked = await self._clear_gate(site, page, unattended)
            if blocked:
                await self._fail_shot(site, page)
                return blocked
            self.site_state[site.id] = "fetching"
            if site.id in self._waited:
                self._waited.discard(site.id)
                await page.goto(url, timeout_s)    # user logged in: reload wanted URL
            if site.cookie_button:
                await page.click_text(site.cookie_button)
            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout_s)
            if click_text:
                await page.bring_to_front()     # background tabs throttle SPA updates
                await self._sleep(self.cfg.click_settle_s)
            if click_text and not await page.click_text(click_text, timeout_s):
                raise RuntimeError(f"text {click_text!r} not found to click")
            if wait_ms:
                await self._sleep(wait_ms / 1000)
            res = FetchResult(status="ok", final_url=await page.url(),
                              title=await page.title(), html=await page.content())
            self.last_error = None
            return res
        except BrowserError as e:
            self.last_error = str(e)
            return FetchResult(status="error", detail=str(e))
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            if page is not None:
                await self._fail_shot(site, page)
            return FetchResult(status="error", detail=self.last_error)
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass

    async def _clear_gate(self, site: SiteConfig, page: Page, unattended: bool = False) -> FetchResult | None:
        """None when the page is usable; a failure result otherwise. Unattended: fail at once, never ask."""
        cfg, start = self.cfg, self._clock()
        waiting = False
        while True:
            state = await self._state(page)
            challenge, login = is_challenge(state), needs_login(state)
            if not (challenge or login):
                return None
            elapsed = self._clock() - start
            if unattended:
                return FetchResult(status="login_timeout" if login else "blocked", final_url=state.url,
                                   title=state.title, detail=f"unattended: {'login' if login else 'challenge'} required")
            if not waiting and (login or elapsed >= cfg.challenge_grace_s):
                # self-resolving challenges get a grace period; logins ask the user at once
                waiting = True
                self._waited.add(site.id)
                self.site_state[site.id] = f"waiting_login:{site.id}"
                await page.bring_to_front()
            limit = cfg.challenge_grace_s + cfg.login_timeout_s
            if elapsed >= limit:
                kind = "login_timeout" if waiting else "blocked"
                return FetchResult(status=kind, final_url=state.url, title=state.title,
                                   detail=f"{'challenge' if challenge else 'login'} not cleared "
                                          f"after {int(elapsed)} s")
            await self._sleep(cfg.poll_interval_s)

    async def _fail_shot(self, site: SiteConfig, page: Page):
        try:
            name = f"{site.id}-{datetime.now():%Y%m%d-%H%M%S}.png"
            await page.screenshot(self.cfg.failures_dir / name)
        except Exception:
            pass

    async def reap_idle(self) -> bool:
        """Close the browser after the idle timeout. True when it was closed."""
        if (self.driver.is_up and self._active == 0
                and self._clock() - self._last_used >= self.cfg.idle_timeout_s):
            await self.driver.close()
            return True
        return False

    async def close(self):
        await self.driver.close()

