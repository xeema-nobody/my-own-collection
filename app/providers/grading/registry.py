"""Grader code -> provider. Add a grader on demand: a parser module + fixture + registry line
(docs/grading-cert-pages.md; ask the user to show the page in a browser first)."""
from app.providers.fetcher import FetcherClient
from app.providers.grading.ace import AceProvider
from app.providers.grading.base import INVALID, CertInfo, CertProvider, clean_cert, now
from app.providers.grading.bgs import BgsProvider
from app.providers.grading.linkonly import LinkOnlyProvider
from app.providers.grading.psa import PsaProvider

# digits allowed per grader (loose; slice 6 adds stricter prefix checks)
CERT_LEN: dict[str, tuple[int, int]] = {"ACE": (5, 7), "PSA": (7, 10), "BGS": (7, 10), "CGC": (7, 10), "SGC": (6, 10)}
ALIASES = {"BECKETT": "BGS", "BVG": "BGS", "BCCG": "BGS", "ACE GRADING": "ACE", "PSA/DNA": "PSA"}


def canon_grader(grader: str | None) -> str:
    g = (grader or "").strip().upper()
    return ALIASES.get(g, g)


def build(grader: str, client: FetcherClient | None = None, transport=None) -> CertProvider | None:
    g = canon_grader(grader)
    if g == "ACE":
        return AceProvider(transport=transport)
    if g == "PSA":
        return PsaProvider(client)
    if g == "BGS":
        return BgsProvider(client)
    if g == "CGC":
        return LinkOnlyProvider("CGC", "https://www.cgccards.com/certlookup/{cert}/",
                                "CGC blocks automated reads: open the report in your browser")
    if g == "SGC":
        return LinkOnlyProvider("SGC", None, "SGC has no confirmed cert link yet")
    return None


def supported(grader: str) -> bool:
    return canon_grader(grader) in CERT_LEN


async def lookup(grader: str, cert: str, client: FetcherClient | None = None, transport=None) -> CertInfo:
    """Never raises. Unknown grader / bad cert -> status invalid (no URL built)."""
    g = canon_grader(grader)
    c = clean_cert(cert)
    lo_hi = CERT_LEN.get(g)
    if c is None or lo_hi is None or not lo_hi[0] <= len(c) <= lo_hi[1]:
        why = "unknown grader" if lo_hi is None else "cert must be digits only"
        return CertInfo(g, (cert or "").strip(), INVALID, None, detail=why, fetched_at=now())
    return await build(g, client, transport).lookup(c)
