"""Parse the raw text of the fixed card regions (collector number, set code, HP). Pure functions, no OCR here."""
import re

LANG_CODES = {"EN", "DE", "FR", "IT", "ES", "PT", "NL", "JP", "JA", "KO"}
NUMBER_RE = re.compile(r"(\d{1,3})\s*/\s*(\d{2,3})")
SET_RE = re.compile(r"[A-Z]{2,5}")


def parse_number(text: str) -> tuple[str, int] | None:
    """("127", 182) from "127/182" (also "127 / 182"). A slash read as a digit ("1271182") is recovered when the
    shape is unambiguous (3 digits, the slash read as 1, 3 digits). Collector numbers never start the total with 0."""
    m = NUMBER_RE.search(text)
    if m:
        return m.group(1).lstrip("0") or "0", int(m.group(2))
    digits = re.sub(r"\D", "", text)
    if len(digits) == 7 and digits[3] == "1":
        return digits[:3].lstrip("0") or "0", int(digits[4:])
    return None


def parse_set_code(text: str) -> str | None:
    """First 2-5 letter upper-case word that is not a language code ("PAR EN" -> "PAR")."""
    for w in SET_RE.findall(text.upper()):
        if w not in LANG_CODES:
            if len(w) > 3 and w[-2:] in LANG_CODES:  # "PAREN": the language code ran into the set code
                w = w[:-2]
            return w
    return None


def parse_hp(text: str) -> int | None:
    m = re.search(r"\d{2,3}", text)
    if not m:
        return None
    v = int(m.group())
    return v if 10 <= v <= 400 and v % 10 == 0 else None
