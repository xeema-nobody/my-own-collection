"""TCGdex catalog adapter (api.tcgdex.net, free, no key). Replacement for the deprecated pokemontcg.io.

Everything in the app is keyed on pokemontcg.io ids (`pokemon:sv3pt5-205`), TCGdex uses others (`sv03.5-205`,
zero-padded numbers), so sets are matched by id, then by name, and cards by number inside the matched set.
Known cards only get their prices refreshed (`_prices_only`): TCGdex rarity/type vocabulary differs and must not
rewrite stored cards. Cards in sets we never imported are created in full. TCGdex has no TCGplayer prices:
only Cardmarket is supplied (`_sources`), a stored TCGplayer price stays as it was.
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_random_exponential

from app.config import settings
from app.providers.catalog.common import _date, _num_sort, norm
from app.providers.catalog.pokemontcg import IncompletePage

log = logging.getLogger(__name__)
CONCURRENCY = 8
BATCH = 40
SOURCES = ("cardmarket",)
SUPERTYPES = {"Pokemon": "Pokémon", "Trainer": "Trainer", "Energy": "Energy"}


@dataclass
class CatalogIndex:
    """What the database already holds: our set docs by external id, card numbers by set id."""
    sets: dict[str, dict] = field(default_factory=dict)
    numbers: dict[str, set[str]] = field(default_factory=dict)


def _retryable(e: BaseException) -> bool:
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(e, httpx.TransportError)


def _key(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", norm(name or "")).strip()


def match_sets(ours: dict[str, dict], theirs: list[dict]) -> dict[str, str]:
    """{our set id: tcgdex set id}: same id first, then same normalised name (card total breaks a tie)."""
    by_id = {t["id"]: t for t in theirs}
    out = {sid: sid for sid in ours if sid in by_id}
    taken = set(out.values())
    by_name: dict[str, list[dict]] = {}
    for t in theirs:
        if t["id"] not in taken:
            by_name.setdefault(_key(t["name"]), []).append(t)
    for sid, s in ours.items():
        if sid in out:
            continue
        cands = by_name.get(_key(s.get("name")), [])
        if len(cands) > 1:
            cands = [t for t in cands if (t.get("cardCount") or {}).get("total") == s.get("total")]
        if len(cands) == 1:
            out[sid] = cands[0]["id"]
            by_name[_key(s.get("name"))] = [t for t in by_name[_key(s.get("name"))] if t["id"] != cands[0]["id"]]
    return out


def card_number(local_id: str) -> str:
    """'001' -> '1' (our numbers are not padded), 'GG41' stays."""
    return re.sub(r"^0+(?=\d)", "", str(local_id))


def _raw_prices(c: dict) -> dict:
    """Embedded-price blocks in the shape `common.extract_prices` reads (EUR floats, Cardmarket only)."""
    cm = (c.get("pricing") or {}).get("cardmarket") or {}
    prices = {"lowPrice": cm.get("low"), "averageSellPrice": cm.get("avg"), "trendPrice": cm.get("trend"),
              "avg7": cm.get("avg7"), "avg30": cm.get("avg30")}
    has = any(prices.values())
    return {"tcgplayer": {}, "cardmarket": {"updatedAt": cm.get("updated"), "url": None, "prices": prices if has else {}}}


def _asset(url: str | None, name: str) -> str | None:
    return f"{url}/{name}" if url else None


def id_prefix(lang: str = "en") -> str:
    """English ids stay `pokemon:`; other languages are namespaced (`pokemon-ja:SV2a-151`), set codes can repeat."""
    return "pokemon" if lang == "en" else f"pokemon-{lang}"


def lang_base_url(lang: str) -> str:
    """`TCGDEX_BASE_URL` ends with the English language segment; swap it for `lang`."""
    return re.sub(r"/[a-z]{2}/?$", "", settings.tcgdex_base_url) + f"/{lang}"


def map_set(s: dict, lang: str = "en") -> dict:
    cc = s.get("cardCount") or {}
    ja = lang != "en"
    return {
        "_id": f"{id_prefix(lang)}:{s['id']}", "tcg": "pokemon", "external_id": s["id"], "name": s["name"],
        "language": lang,
        "series": (s.get("serie") or {}).get("name"), "release_date": _date(s.get("releaseDate")),
        "printed_total": cc.get("official") or None, "total": cc.get("total"),
        "ptcgo_code": s["id"] if ja else (s.get("abbreviation") or {}).get("official"),
        "logo_url": f"{s['logo']}.webp" if s.get("logo") else None,
        "symbol_url": f"{s['symbol']}.webp" if s.get("symbol") else None,
    }


def map_card(c: dict, set_id: str, set_doc: dict, lang: str = "en", name_en: str | None = None) -> dict:
    """Full card doc (same shape as pokemontcg `map_card`) for a card we do not hold yet."""
    number = card_number(c["localId"])
    name = (c.get("name") or "").replace("☆", "★")  # TCGdex writes the Gold Star as a white star
    types = c.get("types") or []
    rules = [c["description"]] if c.get("description") else []
    for part in (c.get("abilities") or []) + (c.get("attacks") or []):
        rules.append(" ".join(filter(None, [part.get("name"), part.get("effect")])))
    v = c.get("variants") or {}
    variants = [k for k, on in (("normal", v.get("normal")), ("reverseHolofoil", v.get("reverse")),
                                ("holofoil", v.get("holo"))) if on]
    img = c.get("image")
    doc = {
        "_id": f"{id_prefix(lang)}:{set_id}-{number}", "tcg": "pokemon", "external_id": f"{set_id}-{number}",
        "name": name, "name_norm": norm(name_en or name), "name_en": name_en, "dex_id": (c.get("dexId") or [None])[0], "number": number, "number_sort": _num_sort(number),
        "supertype": SUPERTYPES.get(c.get("category")), "subtypes": [c["stage"]] if c.get("stage") else [],
        "types": types, "hp": str(c["hp"]) if c.get("hp") else None, "rarity": c.get("rarity"),
        "artist": c.get("illustrator"), "flavor_text": c.get("description"), "rules_text": rules,
        "set": {"id": set_id, "name": set_doc.get("name"), "series": set_doc.get("series"),
                "release_date": set_doc.get("release_date"), "printed_total": set_doc.get("printed_total"),
                "total": set_doc.get("total"), "ptcgo_code": set_doc.get("ptcgo_code"),
                "logo_url": set_doc.get("logo_url"), "symbol_url": set_doc.get("symbol_url")},
        "images": {"small": _asset(img, "low.webp"), "large": _asset(img, "high.webp")} if img else {},
        "variants": variants, "language": lang, "external_ids": {"tcgplayer_url": None, "cardmarket_url": None},
        "updated_at": datetime.now(timezone.utc),
    }
    doc["search_text"] = norm(" ".join(filter(None, [
        name, name_en, set_doc.get("name"), number, f"{number}/{set_doc.get('printed_total')}",
        " ".join(types), " ".join(doc["subtypes"]), c.get("rarity"), " ".join(rules)])))
    if lang != "en":  # norm() drops kana: keep the native text searchable too
        doc["search_text"] += " " + " ".join(filter(None, [name, set_doc.get("name")])).lower()
    doc["_prices_raw"], doc["_sources"] = _raw_prices(c), SOURCES
    return doc


def prices_only(c: dict, set_id: str, lang: str = "en") -> dict:
    """Stub for a card we already hold: just enough for `store_card_prices`; never written to `cards`."""
    cid = f"{set_id}-{card_number(c['localId'])}"
    return {"_id": f"{id_prefix(lang)}:{cid}", "tcg": "pokemon", "external_id": cid, "set": {"id": set_id},
            "_prices_raw": _raw_prices(c), "_sources": SOURCES, "_prices_only": True}


class TcgdexCatalog:
    tcg = "pokemon"

    lang = "en"

    def __init__(self, index: CatalogIndex | None = None, client: httpx.AsyncClient | None = None):
        self.index = index or CatalogIndex()
        self._client = client or httpx.AsyncClient(base_url=lang_base_url(self.lang), timeout=60)
        self._sem = asyncio.Semaphore(CONCURRENCY)
        self._sets: list[dict] | None = None
        self._map: dict[str, str] | None = None

    async def _get(self, path: str, attempts: int = 4) -> dict:
        async for attempt in AsyncRetrying(retry=retry_if_exception(_retryable), stop=stop_after_attempt(attempts),
                                           wait=wait_random_exponential(multiplier=1, max=20), reraise=True):
            with attempt:
                async with self._sem:
                    r = await self._client.get(path)
                r.raise_for_status()
                return r.json()

    async def _tcgdex_sets(self) -> tuple[list[dict], dict[str, str]]:
        if self._sets is None:
            self._sets = await self._get("/sets")
            self._map = match_sets(self.index.sets, self._sets)
        return self._sets, self._map

    async def list_sets(self) -> list[dict]:
        """Known sets as bare `{_id, external_id}` docs (upsert changes nothing), unknown sets in full."""
        sets, mapping = await self._tcgdex_sets()
        by_tid = {tid: sid for sid, tid in mapping.items()}
        out = []
        for s in sets:
            if s["id"] in by_tid:
                sid = by_tid[s["id"]]
                out.append({"_id": f"pokemon:{sid}", "tcg": "pokemon", "external_id": sid})
            else:
                out.append(map_set(await self._get(f"/sets/{s['id']}")))
        return out

    async def _one(self, stub: dict, set_id: str, set_doc: dict | None) -> dict:
        c = await self._get(f"/cards/{stub['id']}")
        return map_card(c, set_id, set_doc) if set_doc else prices_only(c, set_id)

    async def iter_cards(self, set_id: str | None = None, only: set[str] | None = None) -> AsyncIterator[dict]:
        """One request per wanted card. Raises IncompletePage after the rest was yielded if some cards failed."""
        if set_id is None:
            raise ValueError("TCGdex has no whole-catalog listing; pass a set id")
        sets, mapping = await self._tcgdex_sets()
        tid = mapping.get(set_id) or (set_id if any(s["id"] == set_id for s in sets) else None)
        if tid is None:
            log.info("set %s has no TCGdex counterpart, skipped", set_id)
            return
        detail = await self._get(f"/sets/{tid}")
        set_doc = map_set(detail)
        known = self.index.numbers.get(set_id, set())
        upstream = {card_number(c["localId"]) for c in detail.get("cards", [])}
        # Unknown numbers become new cards only while we hold fewer cards than upstream AND our numbers line up
        # with theirs; a set numbered differently (cel25c: '17_A' vs 'CC015') would be duplicated wholesale.
        aligned = len(known & upstream) * 2 >= min(len(known), len(upstream))
        room = set_id not in self.index.sets or (aligned and len(known) < (set_doc["total"] or 0))
        jobs: list[tuple[dict, dict | None]] = []
        for stub in detail.get("cards", []):
            number = card_number(stub["localId"])
            if only is not None and f"pokemon:{set_id}-{number}" not in only:
                continue
            if number in known:
                jobs.append((stub, None))
            elif room:
                jobs.append((stub, set_doc))
        missing: list[tuple[int, int]] = []
        for i in range(0, len(jobs), BATCH):
            chunk = jobs[i:i + BATCH]
            res = await asyncio.gather(*[self._one(s, set_id, d) for s, d in chunk], return_exceptions=True)
            for k, r in enumerate(res):
                if isinstance(r, Exception):
                    log.warning("card %s failed: %s", chunk[k][0].get("id"), r)
                    missing.append((i + k, 1))
                else:
                    yield r
        if missing:
            raise IncompletePage(missing)


class TcgdexJaCatalog(TcgdexCatalog):
    """Japanese cards (`/v2/ja`), namespaced ids `pokemon-ja:{set}-{num}`, language 'ja'.

    No English counterpart sets, so no id/name matching: every wanted set is stored in full. The English species
    name (`name_en`, via the card's dexId and TCGdex's English card list) makes the cards findable by "Slowking".
    `list_sets(wanted)` stores only the chosen sets; `iter_cards(set, only)` skips numbers already held unless `only`
    names them (price refresh).
    """
    lang = "ja"

    def __init__(self, index: CatalogIndex | None = None, client: httpx.AsyncClient | None = None,
                 en_client: httpx.AsyncClient | None = None, wanted: set[str] | None = None):
        super().__init__(index, client)
        self._en = en_client or httpx.AsyncClient(base_url=lang_base_url("en"), timeout=60)
        self._dex: dict[int, str | None] = {}
        self.wanted = wanted

    async def _en_get(self, path: str):
        async for attempt in AsyncRetrying(retry=retry_if_exception(_retryable), stop=stop_after_attempt(4),
                                           wait=wait_random_exponential(multiplier=1, max=20), reraise=True):
            with attempt:
                async with self._sem:
                    r = await self._en.get(path)
                r.raise_for_status()
                return r.json()

    async def name_en(self, dex_id: int | None) -> str | None:
        """Species name for a Pokédex number: the shortest English card name of that dex id (cached)."""
        if not dex_id:
            return None
        if dex_id not in self._dex:
            try:
                names = [c["name"] for c in await self._en_get(f"/cards?dexId={dex_id}") if c.get("name")]
            except Exception as e:  # noqa: BLE001 - a missing English name must not fail the card
                log.warning("english name for dex %s failed: %s", dex_id, e)
                names = []
            self._dex[dex_id] = min(names, key=len) if names else None
        return self._dex[dex_id]

    async def available_sets(self) -> list[dict]:
        """Live brief set list (duplicates by id collapsed: BW3a / BW8a appear twice upstream, first one wins)."""
        seen: dict[str, dict] = {}
        for s in await self._get("/sets"):
            seen.setdefault(s["id"], s)
        return list(seen.values())

    async def list_sets(self) -> list[dict]:
        return [map_set(await self._get(f"/sets/{s['id']}"), self.lang)
                for s in await self.available_sets() if self.wanted is None or s["id"] in self.wanted]

    async def _one(self, stub: dict, set_id: str, set_doc: dict | None) -> dict:
        c = await self._get(f"/cards/{stub['id']}")
        if not set_doc:
            return prices_only(c, set_id, self.lang)
        dex = (c.get("dexId") or [None])[0]
        return map_card(c, set_id, set_doc, self.lang, await self.name_en(dex))

    async def iter_cards(self, set_id: str | None = None, only: set[str] | None = None) -> AsyncIterator[dict]:
        if set_id is None:
            raise ValueError("pass a set id")
        detail = await self._get(f"/sets/{set_id}")
        set_doc = map_set(detail, self.lang)
        known = self.index.numbers.get(set_id, set())
        jobs: list[tuple[dict, dict | None]] = []
        for stub in detail.get("cards", []):
            number = card_number(stub["localId"])
            cid = f"{id_prefix(self.lang)}:{set_id}-{number}"
            if only is not None:
                if cid in only:
                    jobs.append((stub, None if number in known else set_doc))
            elif number not in known:
                jobs.append((stub, set_doc))
        missing: list[tuple[int, int]] = []
        for i in range(0, len(jobs), BATCH):
            chunk = jobs[i:i + BATCH]
            res = await asyncio.gather(*[self._one(s, set_id, d) for s, d in chunk], return_exceptions=True)
            for k, r in enumerate(res):
                if isinstance(r, Exception):
                    log.warning("card %s failed: %s", chunk[k][0].get("id"), r)
                    missing.append((i + k, 1))
                else:
                    yield r
        if missing:
            raise IncompletePage(missing)
