"""Scan / slab with no match: which Japanese set to offer for import (catalog only, never the collection).

The ranking uses what the photo or the grader page gave: the printed set code (`s9` = TCGdex id `S9`), an English set
name through `app/data/ja_set_aliases.json` (TCGdex names ja sets in kana), the printed total (only as a bonus on a
set that already has another signal; many sets share a total) and a typed search. The import itself is the existing
`catalog_ja.import_ja_sets` job, one validated set per call.
"""
import json
import time
from pathlib import Path

from app.providers.catalog.common import norm
from app.services import catalog_ja, jobs

ALIASES: dict[str, list[str]] = json.loads((Path(__file__).parent.parent / "data/ja_set_aliases.json").read_text())
TTL = 600
MAX = 8
_cache: tuple[float, list[dict]] | None = None


async def ja_sets() -> list[dict]:
    """Upstream ja sets with how many cards we hold (live list cached 10 min; the held counts are re-read)."""
    global _cache
    if _cache is None or time.monotonic() - _cache[0] > TTL:
        _cache = (time.monotonic(), await catalog_ja.list_ja_sets())
    return _cache[1]


def reset_cache() -> None:
    global _cache
    _cache = None


async def find_set(set_id: str) -> dict | None:
    return next((s for s in await ja_sets() if s["id"] == set_id), None)


def _alias_ids(set_name: str | None) -> set[str]:
    seen = norm(set_name or "")
    return {i for key, ids in ALIASES.items() if all(w in seen.split() for w in norm(key).split()) for i in ids}


async def suggest(code: str | None = None, total: int | None = None, set_name: str | None = None,
                  q: str | None = None) -> list[dict]:
    """Best ja sets first: `[{id, name, total, printed_total, imported, complete, reason}]`, at most 8; [] without a signal."""
    sets = await ja_sets()
    code_l, q_l, by_alias = (code or "").strip().lower(), (q or "").strip().lower(), _alias_ids(set_name)
    out = []
    for s in sets:
        score, why = 0, []
        if code_l and s["id"].lower() == code_l:
            score, why = score + 10, why + ["set code"]
        if s["id"] in by_alias:
            score, why = score + 6, why + ["set name"]
        if q_l and (q_l in s["id"].lower() or q_l in (s["name"] or "").lower()):
            score, why = score + 5, why + ["search"]
        if score and total and s.get("printed_total") == total:
            score, why = score + 3, why + ["printed total"]
        if score:
            out.append((-score, s["id"], {**s, "reason": ", ".join(why)}))
    return [x[2] for x in sorted(out, key=lambda x: (x[0], x[1]))[:MAX]]


async def import_status(db) -> dict:
    """Progress of the latest ja catalog import: `{state, set, done, expected, failed}`; state idle without one."""
    job = await jobs.current(db, "catalog_import")
    st = (job or {}).get("stats") or {}
    if not job or st.get("language") != "ja" or not st.get("set_ids"):
        return {"state": "idle", "set": None, "done": 0, "expected": None, "failed": []}
    sid = st["set_ids"][0]
    doc = await db.sets.find_one({"_id": f"{catalog_ja.PFX}:{sid}"}) or {}
    done = await db.cards.count_documents({"tcg": "pokemon", "language": "ja", "set.id": sid})
    state = {"running": "running", "ok": "done", "partial": "partial"}.get(job["status"], "error")
    return {"state": state, "set": sid, "done": done, "expected": doc.get("total") or doc.get("printed_total"),
            "failed": st.get("failed_sets") or []}
