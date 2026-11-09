"""Beckett (beckett.com/grading/card-lookup?item_id={cert}&item_type=BGS): Cloudflare + client-side data
-> fetcher only, wait for 'INDIVIDUAL CARD DETAILS'. No card number on the page: match by name + set.
Verified 2026-11-09."""
import re

from bs4 import BeautifulSoup

from app.providers.grading.base import FOUND, NOT_FOUND, CertInfo, grade_from, now
from app.providers.grading.fetched import FetchedProvider

SUBS = {"Centering": "centering", "Corners": "corners", "Edges": "edges", "Surface": "surface"}


class BgsProvider(FetchedProvider):
    grader = "BGS"
    site = "beckett"
    wait_selector = ':text("INDIVIDUAL CARD DETAILS"), :text("No Record found")'

    def cert_url(self, cert: str) -> str:
        return f"https://beckett.com/grading/card-lookup?item_id={cert}&item_type=BGS"

    def parse(self, html: str, cert: str) -> CertInfo:
        url = self.cert_url(cert)
        text = BeautifulSoup(html, "html.parser").get_text("\n")
        lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines()]
        lines = [x for x in lines if x]
        blob = "\n".join(lines)
        if "INDIVIDUAL CARD DETAILS" not in blob:
            return CertInfo("BGS", cert, NOT_FOUND, url, fetched_at=now())

        def after(label: str) -> str | None:
            m = re.search(rf"^{label}\s+(.+)$", blob, re.M)
            return m.group(1).strip() if m else None

        player, set_name = after("Player Name"), after("Set Name")
        if not player:
            return CertInfo("BGS", cert, NOT_FOUND, url, fetched_at=now())
        final = None
        for i, x in enumerate(lines):
            if x.upper() == "FINAL GRADE" and i + 1 < len(lines):
                final = grade_from(lines[i + 1])
                break
        sub = {}
        for k, v in SUBS.items():
            g = grade_from(after(f"{k} Grade"))
            if g is not None:
                sub[v] = g
        year = re.match(r"(\d{4})\b", set_name or "")
        return CertInfo("BGS", cert, FOUND, url, name=player, set_name=set_name,
                        year=int(year.group(1)) if year else None, grade=final, subgrades=sub, fetched_at=now())
