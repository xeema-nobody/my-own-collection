"""PSA (psacard.com/cert/{cert}/psa): free in a browser, Cloudflare 403s plain HTTP -> fetcher only.
Rendered DOM: h1 title, dl > div > dt/dd. Card number only, no printed total. Verified 2026-11-09."""
import re

from bs4 import BeautifulSoup

from app.providers.grading.base import FOUND, NOT_FOUND, CertInfo, grade_from, now, split_number
from app.providers.grading.fetched import FetchedProvider

TIERS = {"10": "GEM MT", "9": "MINT", "8": "NM-MT", "7": "NM", "6": "EX-MT", "5": "EX", "4": "VG-EX",
         "3": "VG", "2": "GOOD", "1": "POOR"}


def _name(soup, d: dict[str, str]) -> str | None:
    """Subject, unless PSA left it generic ('TCG Cards'): then the h1 minus year, brand, number, variety."""
    subject = d.get("Subject")
    if subject and subject.strip().lower() != (d.get("Category") or "").strip().lower():
        return subject
    h1 = soup.find("h1")
    t = re.sub(r"\s+", " ", h1.get_text(" ", strip=True)) if h1 else ""
    for part in (d.get("Year"), d.get("Brand/Title")):
        if part:
            t = t.replace(part, " ", 1)
    t = re.sub(r"#?\b" + re.escape(d.get("Card Number") or "\0") + r"\b", " ", t, count=1)
    if d.get("Variety/Pedigree"):
        t = re.sub(re.escape(d["Variety/Pedigree"]) + r"\s*$", "", t.strip(), flags=re.I)
    return re.sub(r"\s+", " ", t).strip() or None


class PsaProvider(FetchedProvider):
    grader = "PSA"
    site = "psa"
    wait_selector = 'dl, h1:has-text("find that page")'    # report, or PSA 404 for a cert that does not exist

    def cert_url(self, cert: str) -> str:
        return f"https://www.psacard.com/cert/{cert}/psa"

    def parse(self, html: str, cert: str) -> CertInfo:
        url = self.cert_url(cert)
        soup = BeautifulSoup(html, "html.parser")
        d: dict[str, str] = {}
        for dt in soup.select("dl dt"):
            dd = dt.find_next_sibling("dd")
            if dd:
                d[dt.get_text(" ", strip=True)] = dd.get_text(" ", strip=True)
        subject = _name(soup, d)
        if not subject or not re.sub(r"\D", "", d.get("Cert Number", "")).lstrip("0") == cert.lstrip("0"):
            return CertInfo("PSA", cert, NOT_FOUND, url, fetched_at=now())
        number, total = split_number(d.get("Card Number"))
        grade_txt = d.get("Item Grade") or ""
        grade = grade_from(grade_txt)
        year = d.get("Year", "")
        pop: dict[str, int] = {}
        for g in soup.select('div[role="group"]'):
            label = g.find("p")
            val = g.find_all(["p", "a"])
            if label and len(val) > 1:
                key = {"PSA Population": "same", "PSA Pop Higher": "higher"}.get(label.get_text(strip=True))
                num = re.sub(r"[^\d]", "", val[1].get_text()) if key else ""
                if num:
                    pop[key] = int(num)
        if grade is None:
            tier = None
        else:
            tier = re.sub(r"\s*\d+(\.\d)?$", "", grade_txt).strip().upper() or (TIERS.get(str(int(grade))) if grade else None)
        return CertInfo(
            "PSA", cert, FOUND, url, name=subject, number=number, printed_total=total,
            set_name=d.get("Brand/Title"), year=int(year) if re.fullmatch(r"\d{4}", year) else None,
            variant=d.get("Variety/Pedigree") or None, grade=grade, tier=tier, population=pop,
            detail=None if grade is not None else "PSA lists no grade for this cert", fetched_at=now())
