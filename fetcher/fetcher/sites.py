"""Per-site rules. Pure functions over page state so they test without a browser."""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

CHALLENGE_TITLES = ("just a moment", "attention required", "access denied", "are you a robot")
LOGIN_PATH = re.compile(r"/(log-?in|sign-?in)(/|$|\?)", re.I)


@dataclass(frozen=True)
class PageState:
    title: str
    url: str
    text: str


@dataclass(frozen=True)
class SiteConfig:
    id: str
    hosts: tuple[str, ...]
    min_interval_s: float
    cookie_button: str | None = None     # text of a consent button to click, if shown

    def allows(self, url: str) -> bool:
        u = urlparse(url)
        host = (u.hostname or "").lower()
        return u.scheme in ("http", "https") and any(
            host == h or host.endswith("." + h) for h in self.hosts)


def is_challenge(state: PageState) -> bool:
    return state.title.strip().lower().startswith(CHALLENGE_TITLES)


def needs_login(state: PageState) -> bool:
    return bool(LOGIN_PATH.search(urlparse(state.url).path))


SITES: dict[str, SiteConfig] = {s.id: s for s in (
    SiteConfig("pricecharting", ("pricecharting.com",), 3.0),
    SiteConfig("cardmarket", ("cardmarket.com",), 5.0, cookie_button="ONLY REQUIRED"),
    SiteConfig("altxyz", ("alt.xyz",), 3.0),
    SiteConfig("psa", ("psacard.com",), 3.0),         # slab cert pages (5f)
    SiteConfig("beckett", ("beckett.com",), 3.0),
)}

_ID = re.compile(r"^[a-z0-9_-]{1,32}$")


def load_site_file(path: Path | None) -> dict[str, SiteConfig]:
    """Sites from the user's JSON file: [{id, hosts, min_interval_s, cookie_button?}].
    Missing / unreadable file or a bad entry is skipped (never breaks the built-ins)."""
    if path is None:
        return {}
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    out: dict[str, SiteConfig] = {}
    for e in raw if isinstance(raw, list) else []:
        try:
            sid, hosts = e["id"], e["hosts"]
            ok = (isinstance(sid, str) and _ID.match(sid) and isinstance(hosts, list) and hosts
                  and all(isinstance(h, str) and re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", h.lower()) for h in hosts))
            if not ok:
                continue
            gap = max(float(e.get("min_interval_s", 3.0)), 1.0)
            cb = e.get("cookie_button")
            out[sid] = SiteConfig(sid, tuple(h.lower() for h in hosts), gap, cb if isinstance(cb, str) else None)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def all_sites(path: Path | None = None) -> dict[str, SiteConfig]:
    """Built-ins merged with the user file (file wins on the same id). Re-read on every call."""
    return {**SITES, **load_site_file(path)}
