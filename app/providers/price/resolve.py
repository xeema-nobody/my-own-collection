"""Shared fetch flow for adapters: search -> pick -> product, with fetcher failures mapped to statuses."""
from collections.abc import Callable

from app.providers.fetcher import FetcherClient, FetcherUnavailable, FetchResponse
from app.providers.price.base import AdapterResult, Candidate
from app.providers.price.match import pick

FAIL_STATUS = {"login_timeout": "login_timeout", "blocked": "blocked", "error": "error"}


async def safe_fetch(client: FetcherClient, site: str, url: str, **kw) -> FetchResponse | AdapterResult:
    """FetchResponse when ok; else an AdapterResult carrying the failure (never raises)."""
    try:
        r = await client.fetch(site, url, **kw)
    except FetcherUnavailable as e:
        return AdapterResult("error", url=url, detail=str(e))
    if r.status != "ok" or not r.html:
        return AdapterResult(FAIL_STATUS.get(r.status, "error"), url=url, detail=r.detail or r.status)
    return r


async def find_product(card: dict, client: FetcherClient, site: str, search_url: str,
                       parse_search: Callable[[str], list[Candidate]], known_url: str | None,
                       **fetch_kw) -> tuple[str | None, AdapterResult | None]:
    """(product_url, None) when resolved; (None, result) when the caller must return `result`."""
    if known_url:
        return known_url, None
    r = await safe_fetch(client, site, search_url, **fetch_kw)
    if isinstance(r, AdapterResult):
        return None, r
    best, ranked = pick(card, parse_search(r.html))
    if best:
        return best.url, None
    if not ranked:
        return None, AdapterResult("not_found", url=search_url, detail="no search hit matches name/number")
    return None, AdapterResult("needs_match", url=search_url, candidates=ranked[:8],
                               detail="ambiguous or weak match: confirm the product")
