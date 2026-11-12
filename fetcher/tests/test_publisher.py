"""Publisher recipe + runner against a scripted fake page (no network, no Chrome)."""
import pytest

from fetcher.publisher import recipe
from fetcher.publisher.runner import DayCounter, run
from tests.conftest import make_cfg


class PubFake:
    def __init__(self, *, url="https://www.vinted.nl/items/new", text="", dialog=False, status=200,
                 autofill=True, links=None, redirect=True, typed_wrong=False):
        self.u, self.t, self.dialog, self.status = url, text, dialog, status
        self.pinned = "/member/login" in url        # a redirect to login survives goto
        self.vals = {recipe.TID["category"]: "Single trading cards" if autofill else "",
                     recipe.TID["brand"]: "Pokémon"}
        self.link_list = links if links is not None else []
        self.redirect, self.typed_wrong = redirect, typed_wrong
        self.log, self.shots = [], []
        self.item_url = "https://www.vinted.nl/items/999-kleavor-v"

    async def goto(self, url):
        self.log.append(("goto", url))
        if not self.pinned:
            self.u = url
        return self.status

    async def url(self): return self.u
    async def text(self): return self.t

    async def fill(self, testid, value):
        self.log.append(("fill", testid))
        if testid == recipe.TID["price"]:
            value = "€" + value
        self.vals[testid] = value + ("x" if self.typed_wrong and testid == recipe.TID["title"] else "")

    async def click(self, testid):
        self.log.append(("click", testid))
        if testid == recipe.TID["save"] and self.redirect:
            self.u = "https://www.vinted.nl/member/1?promo_shown=true"

    async def click_option(self, text):
        self.vals[recipe.TID["condition"]] = text
        return True

    async def set_files(self, testid, paths): self.log.append(("files", len(paths)))
    async def value(self, testid): return self.vals.get(testid, "")
    async def exists(self, testid): return True
    async def dialog_open(self): return self.dialog
    async def links(self, selector): return self.link_list
    async def screenshot(self, path): self.shots.append(path)


class FakeApi:
    def __init__(self, *items, conflict=False):
        self.items, self.conflict = list(items), conflict
        self.released, self.results = [], []

    async def next(self):
        if self.conflict:
            raise recipe.Guard("queue already has an item in state 'publishing'")
        return self.items.pop(0) if self.items else None

    async def release(self, qid): self.released.append(qid)
    async def result(self, qid, body): self.results.append((qid, body))


def entry(mode="create", url=None, **pl):
    payload = {"title": "Kleavor V SWSH248", "description": "Nice card\nfast shipping", "price": 450,
               "currency": "EUR", "condition": "Very good", "parcel": "small", **pl}
    return {"id": "q1", "mode": mode, "url": url, "open_url": "https://www.vinted.nl/items/new",
            "files": ["publish_tmp/q1/01.jpg", "publish_tmp/q1/02.jpg"], "payload": payload}


async def nosleep(*_a, **_k): pass


def cfg(tmp_path):
    return make_cfg(tmp_path, publish_state=tmp_path / "day.json", publish_min_gap_s=0,
                    publish_action_delay_s=(0, 0))


def fake_links(p):
    p.link_list = [{"href": p.item_url, "text": "Kleavor V SWSH248"}]
    return p


def go(tmp_path, page, api, **kw):
    return run(cfg(tmp_path), page, api, sleep=nosleep, rand=lambda a, b: 0, **kw)


def test_cents_and_parse():
    assert recipe.cents_to_euros(1500) == "15.00" and recipe.cents_to_euros(5) == "0.05"
    assert recipe.parse_cents("€7.00") == 700 and recipe.parse_cents("7,5") == 750
    assert recipe.parse_cents("1.234,50") == 123450 and recipe.parse_cents("") is None


async def test_create_happy_path(tmp_path):
    page, api = fake_links(PubFake()), FakeApi(entry())
    out = await go(tmp_path, page, api)
    assert out == {"published": 1, "released": 0, "failed": 0, "stopped": None}
    assert api.results == [("q1", {"state": "published", "url": page.item_url})]
    assert ("files", 2) in page.log and ("click", recipe.TID["save"]) in page.log
    assert DayCounter(tmp_path / "day.json").count() == 1


async def test_update_skips_photos_and_reports_stored_url(tmp_path):
    stored = "https://www.vinted.nl/items/55-spiritomb"
    page, api = PubFake(), FakeApi(entry("update", stored))
    out = await go(tmp_path, page, api)
    assert out["published"] == 1 and api.results[0][1]["url"] == stored
    assert not any(k == "files" for k, _ in page.log)


async def test_dry_run_never_uploads(tmp_path):
    page, api = PubFake(), FakeApi(entry())
    out = await go(tmp_path, page, api, dry_run=True)
    assert out["released"] == 1 and api.released == ["q1"] and not api.results
    assert ("click", recipe.TID["save"]) not in page.log and page.shots
    assert DayCounter(tmp_path / "day.json").count() == 0


async def test_empty_queue_and_409(tmp_path):
    assert (await go(tmp_path, PubFake(), FakeApi()))["published"] == 0
    out = await go(tmp_path, PubFake(), FakeApi(conflict=True))
    assert "publishing" in out["stopped"]


@pytest.mark.parametrize("kw,why", [
    ({"url": "https://www.vinted.nl/member/login"}, "login"),
    ({"text": "Please verify you are human"}, "blocking"),
    ({"dialog": True}, "dialog"),
    ({"status": 404}, "404"),
    ({"autofill": False}, "auto-filled"),
])
async def test_guards_release_and_stop(tmp_path, kw, why):
    page, api = PubFake(**kw), FakeApi(entry(), entry())
    out = await go(tmp_path, page, api, max_items=2)
    assert why in out["stopped"] and api.released == ["q1"] and not api.results
    assert ("click", recipe.TID["save"]) not in page.log and len(api.items) == 1


async def test_readback_mismatch_releases(tmp_path):
    page, api = PubFake(typed_wrong=True), FakeApi(entry())
    out = await go(tmp_path, page, api)
    assert "title differs" in out["stopped"] and api.released == ["q1"]


async def test_no_redirect_after_upload_marks_failed(tmp_path, monkeypatch):
    import asyncio
    monkeypatch.setattr(asyncio, "sleep", nosleep)
    page, api = PubFake(redirect=False, text="Something went wrong"), FakeApi(entry())
    out = await go(tmp_path, page, api)
    assert out["failed"] == 1 and api.results[0][1]["state"] == "failed" and not api.released


async def test_item_not_found_on_profile_marks_failed(tmp_path):
    page, api = PubFake(links=[{"href": "x", "text": "Other card"}]), FakeApi(entry())
    out = await go(tmp_path, page, api)
    assert out["failed"] == 1 and "not found" in out["stopped"]


async def test_daily_cap_and_max_items(tmp_path):
    c = cfg(tmp_path)
    c.publish_max_per_day = 1
    page, api = fake_links(PubFake()), FakeApi(entry(), entry())
    out = await run(c, page, api, max_items=2, sleep=nosleep, rand=lambda a, b: 0)
    assert out["published"] == 1 and "cap" in out["stopped"] and len(api.items) == 1
