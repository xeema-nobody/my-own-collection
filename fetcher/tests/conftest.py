from pathlib import Path

from fetcher.config import Settings


class FakePage:
    """Scripted page: `states` is a list of (title, url) returned in order, last one sticks."""

    def __init__(self, states, html="<html>ok</html>", on_close=None):
        self.states, self.i, self.html = list(states), 0, html
        self.fronted = self.closed = False
        self.gotos, self.clicked, self.shots = [], [], []
        self.click_ok = True

    def _cur(self):
        return self.states[min(self.i, len(self.states) - 1)]

    async def goto(self, url, timeout_s):
        self.gotos.append(url)

    async def title(self):
        t = self._cur()[0]
        self.i += 1          # each poll advances the script
        return t

    async def url(self):
        return self._cur()[1]

    async def text(self):
        return ""

    async def content(self):
        return self.html

    async def wait_for_selector(self, selector, timeout_s):
        pass

    async def click_text(self, text, timeout_s=2):
        self.clicked.append(text)
        return self.click_ok

    async def click_label(self, label, timeout_s=2):
        self.clicked.append(f"label:{label}")
        return self.click_ok

    async def bring_to_front(self):
        self.fronted = True

    async def screenshot(self, path: Path):
        self.shots.append(path)

    async def close(self):
        self.closed = True


class FakeDriver:
    def __init__(self, *pages):
        self.pages, self.up, self.closes = list(pages), False, 0

    @property
    def is_up(self):
        return self.up

    async def new_page(self):
        self.up = True
        return self.pages.pop(0)

    async def close(self):
        self.up = False
        self.closes += 1


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    async def sleep(self, s):
        self.t += s


def make_cfg(tmp_path, **kw) -> Settings:
    return Settings(failures_dir=tmp_path / "fail", profile_dir=tmp_path / "p", **kw)
