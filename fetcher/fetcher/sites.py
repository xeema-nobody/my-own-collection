"""Per-site rules. Pure functions over page state so they test without a browser."""
import re
from dataclasses import dataclass
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
)}
