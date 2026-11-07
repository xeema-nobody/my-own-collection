"""Parse the text of a graded-card label (PSA, BGS/Beckett, CGC, ACE, SGC) into grader, grade and cert number.
Pure functions over OCR text lines, no OCR here. Every tile of the label is read separately and noisily, so each
function takes *all* lines and votes: the most common reading wins and a single odd read changes nothing."""
import re
from collections import Counter
from dataclasses import dataclass

# Grader words printed on the label (most labels print a logo only: see `infer_grader`).
GRADER_WORDS = (
    ("PSA", re.compile(r"\bPSA\b")),
    ("BGS", re.compile(r"BECKETT|\bBGS\b|BECK[EC]TT")),
    ("CGC", re.compile(r"\bCGC\b|CERTIFIED GUARANTY|\bPRISTINE\b")),
    ("SGC", re.compile(r"\bSGC\b")),
    ("ACE", re.compile(r"\bACE\b|ACE GRADING")),
)
TIER_RE = re.compile(r"\b(GEM\s*MINT|MINT|PRISTINE|NM[- ]?MT|NEAR MINT|EX[- ]?MT|EXCELLENT|VG|GOOD|POOR|FAIR)\b")
GRADE_RE = re.compile(r"(?<![\d.])(10|[1-9](?:\.5)?)(?![\d.])")
SUBGRADE_RE = re.compile(r"CENTER|CORNER|EDGES|SURFACE")
CERT_RE = re.compile(r"(?<!\d)\d(?:[\d ]{4,12}\d)(?!\d)")
CERT_LEN = {"PSA": (7, 9), "BGS": (10, 10), "CGC": (7, 10), "ACE": (6, 6), "SGC": (7, 8)}
ANY_CERT_LEN = (6, 10)


@dataclass
class SlabLabel:
    grader: str | None      # "PSA" | "BGS" | "CGC" | "SGC" | "ACE" | None (not a known grader word)
    grade: float | None
    cert: str | None
    tier: str | None        # "GEM MINT", "MINT" ...
    grader_seen: bool       # the grader name itself was read (False = layout guess, the user confirms)
    is_slab: bool           # tier word + (grade or cert), or a grader word + cert

    def as_dict(self) -> dict:
        return {"grader": self.grader, "grade": self.grade, "cert": self.cert, "tier": self.tier,
                "grader_seen": self.grader_seen}


def _clean(lines: list[str]) -> list[str]:
    return [re.sub(r"\s+", " ", ln.upper()).strip() for ln in lines if ln and ln.strip()]


def find_grader(lines: list[str]) -> str | None:
    votes = Counter()
    for ln in lines:
        for name, rx in GRADER_WORDS:
            if rx.search(ln):
                votes[name] += 1
    if "CGC" in votes and votes["CGC"] == sum(1 for ln in lines if re.search(r"\bPRISTINE\b", ln)) and len(votes) > 1:
        del votes["CGC"]  # "Pristine" alone is a tier word that also appears on other graders' labels
    return votes.most_common(1)[0][0] if votes else None


def find_tier(lines: list[str]) -> str | None:
    votes = Counter()
    for ln in lines:
        m = TIER_RE.search(ln)
        if m:
            votes[re.sub(r"\s+", " ", m.group(1)).replace("GEMMINT", "GEM MINT")] += 1
    return votes.most_common(1)[0][0] if votes else None


TIER_GRADES = {"GEM MINT": (10, 9.5), "MINT": (9, 8.5), "PRISTINE": (10,), "NM-MT": (8, 7, 7.5, 8.5), "NM MT": (8, 7, 7.5, 8.5),
               "NEAR MINT": (8, 7, 7.5, 8.5)}


def plausible(tier: str | None, grade: float | None) -> bool:
    """A grade the tier word allows (GEM MINT is 10 or 9.5, MINT is 9 ...). Unknown tier allows anything."""
    allowed = TIER_GRADES.get((tier or "").replace("GEMMINT", "GEM MINT"))
    return grade is not None and (allowed is None or grade in allowed)


def find_grade(lines: list[str], tier: str | None = None) -> float | None:
    """The overall grade: a lone number (or `number TIER`) on a line without subgrade words. Beckett prints four
    subgrades (centering, corners, edges, surface) next to the overall grade; those lines are skipped."""
    votes = Counter()
    for ln in lines:
        if SUBGRADE_RE.search(ln):
            continue
        toks = ln.split()
        if len(toks) == 1 and GRADE_RE.fullmatch(toks[0]):
            votes[float(toks[0])] += 1
        elif TIER_RE.search(ln):
            m = GRADE_RE.search(TIER_RE.sub(" ", ln))
            if m:
                votes[float(m.group(1))] += 2  # grade and tier words on one line: strongest evidence
    votes = Counter({g: v for g, v in votes.items() if plausible(tier, g)})
    return votes.most_common(1)[0][0] if votes else None


def find_cert(lines: list[str], grader: str | None = None) -> str | None:
    lo, hi = CERT_LEN.get(grader or "", ANY_CERT_LEN)
    # the lone number beside a subgrade row ("EDGES 10 SURFACE 10 0018969667") is still read as one digit run
    votes = Counter()
    for ln in lines:
        for m in CERT_RE.finditer(ln):
            groups = m.group().split()
            # "#011 158690" or "001 8969667": the digits may be one number split by a misread gap, or two numbers
            # side by side. Count the joined run and each trailing run; the cert is the one read most often.
            for k in range(len(groups)):
                digits = "".join(groups[k:])
                if lo <= len(digits) <= hi:
                    votes[digits] += 1
    if not votes:
        return None
    best = max(votes.values())
    top = [c for c, v in votes.items() if v == best]
    return max(top, key=len)  # equal votes: the longer read lost fewer digits


def infer_grader(lines: list[str], tier: str | None, cert: str | None) -> str | None:
    """Labels mostly print a logo, not the company name, so the name is rarely readable. The layout still tells:
    Beckett prints four subgrades and a 10-digit cert, PSA an 8-9 digit cert, ACE a 6-digit cert, CGC a 10-digit
    cert without subgrades. A guess only: `grader_seen` stays False and the user confirms the grader chip."""
    if not cert or not tier:
        return None
    sub = any(SUBGRADE_RE.search(ln) for ln in lines)
    n = len(cert)
    if n == 6:
        return "ACE"
    if sub and n == 10:
        return "BGS"
    if n in (7, 8, 9) and not sub:
        return "PSA"
    if n == 10:
        return "CGC"
    return None


def parse_label(raw_lines: list[str]) -> SlabLabel:
    lines = _clean(raw_lines)
    grader = find_grader(lines)
    tier = find_tier(lines)
    cert = find_cert(lines, grader)
    grade = find_grade(lines, tier)
    seen = grader is not None
    if grader is None:
        grader = infer_grader(lines, tier, cert)
    is_slab = bool((tier and (grade is not None or cert)) or (seen and cert))
    return SlabLabel(grader, grade, cert, tier, seen, is_slab)
