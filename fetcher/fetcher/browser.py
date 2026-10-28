"""Browser driver: real Google Chrome with a dedicated profile, attached over CDP."""
import asyncio
import subprocess
from pathlib import Path
from typing import Protocol

import httpx
from playwright.async_api import Browser, Playwright, async_playwright
from playwright.async_api import Page as PwPage

from fetcher.config import Settings


class BrowserError(RuntimeError):
    pass


class Page(Protocol):
    async def goto(self, url: str, timeout_s: float) -> None: ...
    async def title(self) -> str: ...
    async def url(self) -> str: ...
    async def text(self) -> str: ...
    async def content(self) -> str: ...
    async def wait_for_selector(self, selector: str, timeout_s: float) -> None: ...
    async def click_text(self, text: str, timeout_s: float = 2) -> bool: ...
    async def bring_to_front(self) -> None: ...
    async def screenshot(self, path: Path) -> None: ...
    async def close(self) -> None: ...


class Driver(Protocol):
    @property
    def is_up(self) -> bool: ...
    async def new_page(self) -> Page: ...
    async def close(self) -> None: ...


class ChromePage:
    def __init__(self, page: PwPage):
        self._p = page

    async def goto(self, url, timeout_s):
        await self._p.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)

    async def title(self):
        try:
            return await self._p.title()
        except Exception:      # mid-navigation
            return ""

    async def url(self):
        return self._p.url

    async def text(self):
        try:
            return await self._p.inner_text("body", timeout=3000)
        except Exception:
            return ""

    async def content(self):
        return await self._p.content()

    async def wait_for_selector(self, selector, timeout_s):
        await self._p.wait_for_selector(selector, timeout=timeout_s * 1000)

    async def click_text(self, text, timeout_s=2):
        try:
            await self._p.get_by_text(text, exact=True).first.click(timeout=timeout_s * 1000)
            return True
        except Exception:
            return False

    async def bring_to_front(self):
        await self._p.bring_to_front()

    async def screenshot(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        await self._p.screenshot(path=str(path))

    async def close(self):
        await self._p.close()


class ChromeCdpDriver:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self._proc: subprocess.Popen | None = None
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    @property
    def is_up(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def _cdp_alive(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=1) as c:
                return (await c.get(f"http://127.0.0.1:{self.cfg.cdp_port}/json/version")).is_success
        except httpx.HTTPError:
            return False

    async def _start(self):
        cfg = self.cfg
        if not Path(cfg.chrome_path).exists():
            raise BrowserError(f"Chrome not found at {cfg.chrome_path} (set FETCHER_CHROME_PATH)")
        if not await self._cdp_alive():      # else: attach to leftover instance of ours
            cfg.profile_dir.mkdir(parents=True, exist_ok=True)
            self._proc = subprocess.Popen(
                [cfg.chrome_path, f"--remote-debugging-port={cfg.cdp_port}",
                 f"--user-data-dir={cfg.profile_dir}", "--no-first-run",
                 "--no-default-browser-check", "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(40):
                if await self._cdp_alive():
                    break
                if self._proc.poll() is not None:
                    raise BrowserError("Chrome exited at start (profile already in use?)")
                await asyncio.sleep(0.5)
            else:
                raise BrowserError("Chrome did not open the debugging port in 20 s")
        self._pw = await async_playwright().start()
        last: Exception | None = None
        for _ in range(3):
            try:
                self._browser = await self._pw.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{cfg.cdp_port}")
                return
            except Exception as e:      # spike: first attach can fail, retry works
                last = e
                await asyncio.sleep(1.5)
        await self.close()
        raise BrowserError(f"cannot attach to Chrome over CDP: {last}")

    async def new_page(self) -> Page:
        async with self._lock:
            if not self.is_up:
                await self.close()
                await self._start()
            ctx = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
            return ChromePage(await ctx.new_page())

    async def close(self):
        browser, pw, proc = self._browser, self._pw, self._proc
        self._browser = self._pw = self._proc = None
        if browser is not None:
            try:
                s = await browser.new_browser_cdp_session()
                await s.send("Browser.close")
            except Exception:
                pass
        if pw is not None:
            try:
                await pw.stop()
            except Exception:
                pass
        if proc is not None:
            try:
                await asyncio.to_thread(proc.wait, 5)
            except subprocess.TimeoutExpired:
                proc.terminate()
