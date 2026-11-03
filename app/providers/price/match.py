"""Pick the right product for a card among search hits. Pure scoring, no I/O."""
import re
import unicodedata

from app.providers.price.base import Candidate

ACCEPT_SCORE = 0.8      # top candidate must reach this ...
ACCEPT_MARGIN = 0.15    # ... and beat the runner-up by this much, else the user confirms
VARIANT_PENALTY = 0.3   # '[Metal]', '[Jumbo]', '(Reverse Holo)'... when the card name has none
STOP = {"pokemon", "tcg", "card", "cards", "the", "of", "and", "set", "scarlet", "violet",
        "sword", "shield", "sun", "moon", "japanese"}


# sub-set labels shops drop ('Celebrations: Classic Collection' is filed under 'Pokemon Celebrations')
SET_NOISE = {"classic", "collection"}

LANG_WORDS = {"japanese": "ja", "korean": "ko", "chinese": "zh", "german": "de", "french": "fr",
              "italian": "it", "spanish": "es", "portuguese": "pt"}


def language_of(text: str) -> str:
    """Language named in a set/product label ('Pokemon Korean Scarlet & Violet 151' -> 'ko'); else 'en'."""
    return next((c for w, c in LANG_WORDS.items() if w in norm(text).split()), "en")


STAR = "\u2605"    # pokemontcg marks vintage Gold Star prints with a trailing star in the name


def search_name(name: str) -> str:
    """Name as sites write it: 'Umbreon \u2605' -> 'Umbreon Gold Star'."""
    return re.sub(r"\s+", " ", name.replace(STAR, " Gold Star ")).strip()


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").replace(STAR, " gold star ")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def norm_number(n: str | None) -> str:
    n = (n or "").split("/")[0].strip().lower()
    m = re.fullmatch(r"([a-z]*)0*(\d+)([a-z]*)", n)
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else n


def _tokens(s: str) -> set[str]:
    return {t for t in norm(s).split() if t not in STOP}


def strip_variant(name: str) -> tuple[str, bool]:
    """('Mew Ex [Metal]') -> ('mew ex', True)"""
    base = re.sub(r"[\[(][^\])]*[\])]", " ", name)
    return norm(base), base.strip() != name.strip()


def _core(name: str) -> tuple[str, bool]:
    """(base name without the star marker, has a real variant tag). '[Gold Star]' is not a variant:
    PriceCharting writes 'Umbreon [Gold Star]' for one print and plain 'Umbreon' for another."""
    base, has_variant = strip_variant(re.sub(r"\[\s*gold star\s*\]", " ", name, flags=re.I).replace(STAR, " "))
    return re.sub(r"\bgold star\b", " ", base).strip(), has_variant


def score(card: dict, cand: Candidate) -> float:
    """0..1. Number, base name and language must match, else 0; set overlap decides the rest."""
    if norm_number(cand.number) != norm_number(card.get("number")):
        return 0.0
    if cand.language != (card.get("language") or "en"):
        return 0.0
    card_base, card_has_variant = _core(card["name"])
    cand_base, cand_has_variant = _core(cand.name)
    if cand_base != card_base:
        return 0.0
    want = _tokens((card.get("set") or {}).get("name") or "")
    want = (want - SET_NOISE) or want
    have = _tokens(cand.set_name)
    set_part = len(want & have) / len(want) if want else 0.5
    s = 0.6 + 0.4 * set_part
    if cand_has_variant and not card_has_variant:
        s -= VARIANT_PENALTY
    return round(max(s, 0.0), 3)


def rank(card: dict, cands: list[Candidate]) -> list[Candidate]:
    for c in cands:
        c.score = score(card, c)
    return sorted((c for c in cands if c.score > 0), key=lambda c: c.score, reverse=True)


def pick(card: dict, cands: list[Candidate]) -> tuple[Candidate | None, list[Candidate]]:
    """(accepted, ranked). accepted is None when empty or ambiguous: caller returns needs_match."""
    ranked = rank(card, cands)
    if not ranked or ranked[0].score < ACCEPT_SCORE:
        return None, ranked
    if len(ranked) > 1 and ranked[0].score - ranked[1].score < ACCEPT_MARGIN:
        return None, ranked
    return ranked[0], ranked
