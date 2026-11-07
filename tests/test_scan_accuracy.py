"""Local OCR accuracy on real phone photos. The photos are private and git-ignored (tests/private/scan_samples/ with
a labels.json of file -> {name, number, total}; a bare string is just the name); without them this module is skipped, so CI and fresh clones pass.
Run with `-s` to see the hit rate. Card names come from the labels plus decoys (no database needed)."""
import json
import shutil
from pathlib import Path

import pytest

from app.providers.ocr.tesseract import TesseractOcr
from app.services import scan

DIR = Path(__file__).parent / "private" / "scan_samples"
_RAW = json.loads((DIR / "labels.json").read_text()) if (DIR / "labels.json").exists() else {}
LABELS = {f: (v if isinstance(v, dict) else {"name": v}) for f, v in _RAW.items()}
DECOYS = ["lampent", "litwick", "drakloak", "dreepy", "poliwhirl", "poliwrath", "pikachu v", "ferrothorn", "iris",
          "clive", "grant", "barry", "piers", "lisia", "choy", "ralts", "tulip", "eevee", "charizard"]
MIN_HIT_RATE = 0.8
MIN_NUMBER_RATE = 0.8  # collector number read right (measured 14/15 on the first set)

pytestmark = pytest.mark.skipif(not LABELS or not shutil.which("tesseract"), reason="no private photos / tesseract")


class NamesDb:
    class cards:  # noqa: N801
        @staticmethod
        async def distinct(*_a, **_k):
            return sorted({v['name'] for v in LABELS.values()} | set(DECOYS) | {"dragapult", "dragapult v", "chandelure v"})


async def test_hit_rate_on_real_photos(capsys):
    scan.reset_names_cache()
    hits, misses = 0, []
    for fname, label in sorted(LABELS.items()):
        expected = label["name"]
        _, matches = await scan.read_until_match(NamesDb, TesseractOcr(), (DIR / fname).read_bytes())
        found = {n for n, _ in matches}
        found |= {n for n, _ in scan.with_suffix_variants(await NamesDb.cards.distinct(), [(m, 1.0) for m in found])}
        if expected in found:
            hits += 1
        else:
            misses.append((fname, expected, sorted(found)))
    rate = hits / len(LABELS)
    with capsys.disabled():
        print(f"\nscan OCR hit rate: {hits}/{len(LABELS)} = {rate:.0%}; misses: {misses}")
    scan.reset_names_cache()
    assert rate >= MIN_HIT_RATE


async def test_collector_number_read_rate_on_real_photos(capsys):
    labelled = {f: v for f, v in LABELS.items() if v.get("number")}
    if not labelled:
        pytest.skip("no numbers in labels.json")
    hits, misses = 0, []
    for fname, label in sorted(labelled.items()):
        got = await TesseractOcr().read_fields((DIR / fname).read_bytes())
        if got.number == str(label["number"]).lstrip("0"):
            hits += 1
        else:
            misses.append((fname, label["number"], got.number))
    rate = hits / len(labelled)
    with capsys.disabled():
        print(f"\ncollector number read rate: {hits}/{len(labelled)} = {rate:.0%}; misses: {misses}")
    assert rate >= MIN_NUMBER_RATE
