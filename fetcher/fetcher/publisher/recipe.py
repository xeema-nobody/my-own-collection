"""Vinted form recipe (docs/vinted-sell-flow.md) against a small page protocol.

Steps never decide to continue past something odd: any surprise raises `Guard`, the runner
releases the item and stops. Nothing here solves or dismisses a CAPTCHA, login or dialog.
"""
import asyncio
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

TID = {
    "photos": "add-photos-input", "title": "title--input", "description": "description--input",
    "category": "catalog-select-dropdown-input", "brand": "brand-select-dropdown-input",
    "condition": "category-condition-single-list-input", "price": "price-input--input",
    "save": "upload-form-save-button",
}
PARCEL_TID = {"small": "1-package-size--cell", "medium": "2-package-size--cell",
              "large": "3-package-size--cell"}
BLOCK_URL = ("/member/login", "/member/signup", "/member/general/login", "/session", "/signup")
BLOCK_TEXT = ("captcha", "verify you are human", "are you a robot", "unusual activity",
              "access denied", "datadome", "log in to continue", "log in or sign up")
ITEM_HREF = "a[href*='/items/']"


class Guard(RuntimeError):
    """Something unexpected on the page: stop, release the item, tell the user."""


class Mismatch(Guard):
    pass


class PubPage(Protocol):
    async def goto(self, url: str) -> int: ...          # HTTP status (0 unknown)
    async def url(self) -> str: ...
    async def text(self) -> str: ...
    async def fill(self, testid: str, value: str) -> None: ...
    async def click(self, testid: str) -> None: ...
    async def click_option(self, text: str) -> bool: ...
    async def set_files(self, testid: str, paths: list[str]) -> None: ...
    async def value(self, testid: str) -> str: ...
    async def exists(self, testid: str) -> bool: ...
    async def dialog_open(self) -> bool: ...
    async def links(self, selector: str) -> list[dict]: ...
    async def screenshot(self, path: Path) -> None: ...


def cents_to_euros(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def parse_cents(shown: str) -> int | None:
    m = re.search(r"\d[\d.,]*", shown or "")
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return int((Decimal(s) * 100).to_integral_value())
    except InvalidOperation:
        return None


async def check_page(page: PubPage) -> None:
    """Raise Guard on login, CAPTCHA / bot check or any open dialog."""
    path = urlsplit(await page.url()).path.lower()
    if any(path.startswith(b) or b in path for b in BLOCK_URL):
        raise Guard(f"login or session page ({path})")
    low = (await page.text()).lower()
    for w in BLOCK_TEXT:
        if w in low:
            raise Guard(f"blocking page text: '{w}'")
    if await page.dialog_open():
        raise Guard("unexpected dialog open")


def _norm(s: str) -> str:
    return "\n".join(line.rstrip() for line in s.replace("\r\n", "\n").strip().splitlines())


async def fill_form(page: PubPage, d: dict, pause) -> None:
    """Fill the form from the claimed queue entry `d` (payload + mode + files), then read back."""
    p, create = d["payload"], d["mode"] == "create"
    status = await page.goto(d["open_url"])
    if status == 404:
        raise Guard("edit page 404 (stored link?)")
    await pause()
    await check_page(page)
    if create and d["files"]:
        await page.set_files(TID["photos"], d["files"])
        await pause(2.0)
        await check_page(page)
    await page.fill(TID["title"], p["title"])
    await pause()
    await page.fill(TID["description"], p["description"])
    await pause()
    await check_page(page)
    if create:
        await pause(1.5)                      # Vinted auto-fills category + brand from the title
        for key, want in (("category", "single trading cards"), ("brand", "pok")):
            if want not in (await page.value(TID[key])).lower():
                raise Guard(f"{key} not auto-filled as expected")
        await page.click(TID["condition"])
        await pause()
        if not await page.click_option(p["condition"]):
            raise Guard(f"condition option '{p['condition']}' not found")
        await pause()
        await check_page(page)                # 'Item must be unused' dialog lands here
        await page.click(PARCEL_TID[p["parcel"]])
        await pause()
    await page.fill(TID["price"], cents_to_euros(p["price"]))
    await pause()
    await check_page(page)
    await read_back(page, p, create)


async def read_back(page: PubPage, p: dict, create: bool) -> None:
    if (await page.value(TID["title"])).strip() != p["title"].strip():
        raise Mismatch("title differs after typing")
    if _norm(await page.value(TID["description"])) != _norm(p["description"]):
        raise Mismatch("description differs after typing")
    if parse_cents(await page.value(TID["price"])) != p["price"]:
        raise Mismatch("price differs after typing")
    if create and p["condition"].lower() not in (await page.value(TID["condition"])).lower():
        raise Mismatch("condition differs")


async def upload(page: PubPage, d: dict, pause, timeout_s: float = 30, tick_s: float = 1) -> str:
    """Click Upload/Save, wait for the profile redirect, return the canonical item URL."""
    p = d["payload"]
    await page.click(TID["save"])
    waited = 0.0
    while "/member/" not in await page.url():
        await check_page(page)
        if waited >= timeout_s:
            raise Guard(f"no redirect after Upload: {(await page.text())[:200]!r}")
        await asyncio.sleep(tick_s)
        waited += tick_s
    await pause(2.0)
    await check_page(page)
    if d["mode"] == "update":
        return d["url"]                       # edit keeps the item URL
    head = p["title"][:25].lower()
    for link in await page.links(ITEM_HREF):
        if link["text"].lower().startswith(head) or head in link["text"].lower():
            await page.goto(link["href"])
            await pause()
            u = await page.url()
            if "/items/" in u:
                return u.split("?")[0].split("#")[0]
    raise Guard("uploaded item not found on the profile page")
