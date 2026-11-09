"""ACE Grading (acegrading.com): server-rendered cert page, plain httpx, no bot wall.
Verified 2026-11-08 against tests/fixtures/cert/ace_*.html. An unknown cert is HTTP 200 with a
generic 'Verify Certification Number' title (no 'Cert #')."""
import re

import httpx
from bs4 import BeautifulSoup

from app.providers.grading.base import (
    FOUND, NOT_FOUND, UNAVAILABLE, CertInfo, clean_cert, grade_from, now, split_number)

BASE = "https://acegrading.com/cert/"
UA = "my-own-collection/1.0 (personal collection manager; one lookup per scan)"
DETAIL_KEYS = ("Label", "Name", "Release Year", "Set", "Number", "Language", "Variant")


def cert_url(cert: str) -> str:
    return BASE + cert


def _text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True))


def _details(soup) -> dict[str, str]:
    """'Card Details' block: 'Label Standard Name Charizard V Release Year 2022 Set ...' -> dict."""
    head = next((h for h in soup.find_all("h2") if _text(h) == "Card Details"), None)
    if head is None:
        return {}
    blob = _text(head.parent)
    blob = blob.split("Card Details", 2)[-1] if blob.count("Card Details") > 1 else blob.replace("Card Details", "", 1)
    pat = r"(?:^|\s)(" + "|".join(re.escape(k) for k in DETAIL_KEYS) + r")\s"
    parts = re.split(pat, " " + blob.strip() + " ")
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def parse(html: str, cert: str) -> CertInfo:
    url = cert_url(cert)
    soup = BeautifulSoup(html, "html.parser")
    title = _text(soup.title) if soup.title else ""
    if "Cert #" not in title:
        return CertInfo("ACE", cert, NOT_FOUND, url, detail="ACE has no such cert", fetched_at=now())
    d = _details(soup)
    number, total = split_number(d.get("Number"))
    sub: dict[str, float] = {}
    for h5 in soup.find_all("h5"):
        label = _text(h5).lower()
        if label in ("surface", "centering", "edges", "corners"):
            box = h5.find_next_sibling("div")
            g = grade_from(_text(box)) if box else None
            if g is not None:
                sub[label] = g
    grade = tier = None
    gh = next((h for h in soup.find_all("h3") if _text(h).lower() == "grade"), None)
    if gh is not None:
        tier_node = gh.find_next("h5")
        tier = _text(tier_node).upper() if tier_node else None
        box = tier_node.find_next_sibling("div") if tier_node else None
        grade = grade_from(_text(box)) if box else None
    pop: dict[str, int] = {}
    for h3 in soup.find_all("h3"):
        key = {"population": "same", "population higher": "higher", "total submitted": "submitted"}.get(_text(h3).lower())
        h4 = h3.find_next("h4") if key else None
        if h4 and re.fullmatch(r"\d+", _text(h4)):
            pop[key] = int(_text(h4))
    name = d.get("Name")
    if not name:
        m = re.search(r"Cert #\d+ - (?:\d{4} - )?(.*?) - ", title)
        name = m.group(1) if m else None
    return CertInfo(
        "ACE", cert, FOUND, url, name=name, number=number, printed_total=total,
        set_name=d.get("Set"), year=int(d["Release Year"]) if re.fullmatch(r"\d{4}", d.get("Release Year", "")) else None,
        language=d.get("Language"), variant=d.get("Variant"), grade=grade, tier=tier,
        subgrades=sub, population=pop, fetched_at=now())


class AceProvider:
    grader = "ACE"

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None, timeout: float = 8.0):
        self._transport, self._timeout = transport, timeout

    async def lookup(self, cert: str) -> CertInfo:
        cert = clean_cert(cert) or ""
        url = cert_url(cert)
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport, headers={"User-Agent": UA},
                                         follow_redirects=False) as c:
                r = await c.get(url)
        except httpx.HTTPError as e:
            return CertInfo("ACE", cert, UNAVAILABLE, url, detail=f"ACE page unreachable: {type(e).__name__}", fetched_at=now())
        if r.status_code != 200:
            return CertInfo("ACE", cert, UNAVAILABLE, url, detail=f"ACE page HTTP {r.status_code}", fetched_at=now())
        return parse(r.text, cert)
