"""Queue worker: claim -> fill -> read back -> (dry run: release | upload -> report)."""
import asyncio
import json
import logging
import random
from datetime import date
from pathlib import Path

import httpx

from fetcher.browser import ChromeCdpDriver, ChromePage
from fetcher.config import Settings
from fetcher.notify import TITLE, osascript_show
from fetcher.publisher import recipe
from fetcher.publisher.recipe import Guard, PubPage

log = logging.getLogger("fetcher.publisher")
REPO_ROOT = Path(__file__).resolve().parents[3]


class PwPubPage:
    """PubPage over a raw Playwright page (real Chrome, CDP)."""

    def __init__(self, page, nav_timeout_s: float):
        self._p, self._t = page, nav_timeout_s * 1000

    async def goto(self, url):
        r = await self._p.goto(url, wait_until="domcontentloaded", timeout=self._t)
        return r.status if r else 0

    async def url(self):
        return self._p.url

    async def text(self):
        try:
            return await self._p.inner_text("body", timeout=3000)
        except Exception:
            return ""

    def _t_(self, testid):
        return self._p.get_by_test_id(testid).first

    async def fill(self, testid, value):
        loc = self._t_(testid)
        await loc.click(timeout=10000)
        await loc.fill("", timeout=10000)
        await loc.press_sequentially(value, delay=random.randint(8, 25), timeout=120000)

    async def click(self, testid):
        await self._t_(testid).click(timeout=10000)

    async def click_option(self, text):
        try:
            await self._p.get_by_text(text, exact=True).first.click(timeout=5000)
            return True
        except Exception:
            return False

    async def set_files(self, testid, paths):
        await self._p.locator(f"[data-testid='{testid}']").first.set_input_files(paths, timeout=60000)

    async def value(self, testid):
        loc = self._t_(testid)
        try:
            return await loc.input_value(timeout=3000)
        except Exception:
            try:
                return await loc.inner_text(timeout=3000)
            except Exception:
                return ""

    async def exists(self, testid):
        return await self._p.get_by_test_id(testid).count() > 0

    async def dialog_open(self):
        return await self._p.locator("[role=dialog]:visible, dialog[open]").count() > 0

    async def links(self, selector):
        return await self._p.eval_on_selector_all(
            selector, "els => els.map(e => ({href: e.href, text: (e.getAttribute('title') || e.innerText || '').trim()}))")

    async def screenshot(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        await self._p.screenshot(path=str(path))


class Api:
    def __init__(self, base: str):
        self.c = httpx.AsyncClient(base_url=base + "/api/publish", timeout=30)

    async def next(self) -> dict | None:
        r = await self.c.post("/queue/next")
        if r.status_code == 409:
            raise Guard("queue already has an item in state 'publishing' (release or report it first)")
        r.raise_for_status()
        return r.json()

    async def release(self, qid):
        await self.c.post(f"/queue/{qid}/release")

    async def result(self, qid, body):
        r = await self.c.post(f"/queue/{qid}/result", json=body)
        r.raise_for_status()

    async def close(self):
        await self.c.aclose()


class DayCounter:
    """Published items per calendar day, kept on disk so the cap survives restarts."""

    def __init__(self, path: Path):
        self.path = path

    def count(self) -> int:
        try:
            st = json.loads(self.path.read_text())
            return st["n"] if st["day"] == date.today().isoformat() else 0
        except (OSError, ValueError, KeyError):
            return 0

    def add(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"day": date.today().isoformat(), "n": self.count() + 1}))


async def run(cfg: Settings, page: PubPage, api, *, dry_run=False, max_items=1, notify=None,
              sleep=asyncio.sleep, rand=random.uniform, counter: DayCounter | None = None) -> dict:
    """Work up to `max_items` queue entries. Returns {published, released, failed, stopped}."""
    counter = counter or DayCounter(cfg.publish_state)

    async def pause(base: float | None = None):
        lo, hi = cfg.publish_action_delay_s
        await sleep(base if base is not None else rand(lo, hi))

    out = {"published": 0, "released": 0, "failed": 0, "stopped": None}
    for n in range(max_items):
        if not dry_run and counter.count() >= cfg.publish_max_per_day:
            out["stopped"] = f"daily cap {cfg.publish_max_per_day} reached"
            break
        try:
            d = await api.next()
        except Guard as g:
            out["stopped"] = str(g)
            break
        if not d:
            break
        qid, label = d["id"], d["payload"]["title"]
        try:
            await recipe.fill_form(page, d, pause)
            if dry_run:
                await page.screenshot(cfg.failures_dir / f"dryrun-{qid}.png")
                await api.release(qid)
                out["released"] += 1
                continue
            url = await recipe.upload(page, d, pause)
            await api.result(qid, {"state": "published", "url": url})
            counter.add()
            out["published"] += 1
        except Guard as g:
            try:
                await page.screenshot(cfg.failures_dir / f"publish-{qid}.png")
            except Exception:
                pass
            if "no redirect after Upload" in str(g) or "uploaded item not found" in str(g):
                # Upload was clicked: do not re-queue blindly; mark failed so the user checks Vinted
                await api.result(qid, {"state": "failed", "error": str(g)[:500]})
                out["failed"] += 1
            else:
                await api.release(qid)
                out["released"] += 1
            out["stopped"] = f"{label}: {g}"
            break
        if n + 1 < max_items:
            await sleep(cfg.publish_min_gap_s + rand(0, cfg.publish_min_gap_s / 2))
    if notify and (out["stopped"] or out["published"]):
        await notify(TITLE, out["stopped"] or f"Vinted: {out['published']} published")
    return out


async def main(cfg: Settings, dry_run: bool, max_items: int) -> int:
    driver, api = ChromeCdpDriver(cfg), Api(cfg.app_url)
    try:
        cp: ChromePage = await driver.new_page()      # type: ignore[assignment]
        page = PwPubPage(cp._p, cfg.nav_timeout_s)
        res = await run(cfg, page, api, dry_run=dry_run, max_items=max_items,
                        notify=osascript_show if cfg.notify_enabled else None)
    finally:
        await api.close()
        await driver.close()
    print(json.dumps(res))
    return 1 if res["stopped"] else 0
