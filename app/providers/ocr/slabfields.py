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
CERT_LEN = {"PSA": (7, 9), "BGS": (10, 10), "CGC": (7, 10), "ACE": (6, 7), "SGC": (7, 8)}  # digit runs worth voting on
CERT_SURE = {"PSA": (8, 9), "BGS": (10, 10), "CGC": (10, 10), "ACE": (6, 6), "SGC": (7, 8)}  # lengths a real cert has (every ACE sample is 6 digits)
ANY_CERT_LEN = (6, 10)


@dataclass
class SlabLabel:
    grader: str | None      # "PSA" | "BGS" | "CGC" | "SGC" | "ACE" | None (not a known grader word)
    grade: float | None
    cert: str | None
    tier: str | None        # "GEM MINT", "MINT" ...
    grader_seen: bool       # the grader name itself was read (False = layout guess, the user confirms)
    is_slab: bool           # tier word + (grade or cert), or a grader word + cert
    cert_sure: bool = True  # the cert has a length the grader prints (False = a digit was probably dropped or added)
    cert_alt: tuple = ()    # other cert reads, best first: tried when the first one is not found

    def as_dict(self) -> dict:
        d = {"grader": self.grader, "grade": self.grade, "cert": self.cert, "tier": self.tier,
             "grader_seen": self.grader_seen}
        if self.cert and not self.cert_sure:
            d["cert_sure"] = False
        if self.cert_alt:
            d["cert_alt"] = list(self.cert_alt)
        return d


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


def cert_sure(grader: str | None, cert: str) -> bool:
    """The cert has a length (and prefix) this grader prints. With no grader: any grader's."""
    def ok(g: str) -> bool:
        lo, hi = CERT_SURE[g]
        return lo <= len(cert) <= hi and (g != "BGS" or cert.startswith("00"))
    return ok(grader) if grader in CERT_SURE else any(ok(g) for g in CERT_SURE if g != "SGC")


def cert_candidates(lines: list[str], grader: str | None = None, targeted: list[str] | None = None) -> list[tuple[str, bool]]:
    """Digit runs read as a cert, best first, as (cert, sure). `targeted` = lines from the cert region alone (digits
    only): their votes count triple, the label lines also carry year / card number runs ("2023 151") that pass for a
    cert. Order: sure length first, then votes, then the longer read (it lost fewer digits)."""
    lo, hi = CERT_LEN.get(grader or "", ANY_CERT_LEN)
    votes: Counter = Counter()
    for weight, group in ((1, lines), (3, targeted or [])):
        for ln in group:
            for m in CERT_RE.finditer(ln):
                # "#011 158690" or "001 8969667": one number split by a misread gap, or two numbers side by side:
                # count the joined run and each trailing run
                groups = m.group().split()
                for k in range(len(groups)):
                    digits = "".join(groups[k:])
                    if lo <= len(digits) <= hi:
                        votes[digits] += weight
    for c, v in list(votes.items()):  # Beckett prints 00 first and the first 0 is the one tesseract turns into a 9 / 8 / 6
        if len(c) == 10 and c[1] == "0" and c[0] != "0" and grader in (None, "BGS"):
            votes["0" + c[1:]] += v
    ranked = sorted(votes, key=lambda c: (cert_sure(grader, c), votes[c], len(c)), reverse=True)
    return [(c, cert_sure(grader, c)) for c in ranked]


def find_cert(lines: list[str], grader: str | None = None) -> str | None:
    got = cert_candidates(lines, grader)
    return got[0][0] if got else None


def grader_for_cert(lines: list[str], cert: str | None) -> str | None:
    """Labels mostly print a logo, not the company name, so the name is rarely readable. The cert length still tells:
    ACE 5-7 digits, PSA 8-9, Beckett 10 starting 00 (and four subgrades), CGC 10 without subgrades. SGC is never
    inferred (its range overlaps). A guess only: `grader_seen` stays False and the user confirms the grader chip."""
    if not cert:
        return None
    sub = any(SUBGRADE_RE.search(ln) for ln in lines)
    n = len(cert)
    if n in (6, 7):
        return "ACE"
    if n == 10 and (sub or cert.startswith("00")):
        return "BGS"
    if n in (8, 9) and not sub:
        return "PSA"
    if n == 10:
        return "CGC"
    return None


def infer_grader(lines: list[str], tier: str | None, cert: str | None) -> str | None:
    return grader_for_cert(lines, cert) if cert and tier else None


def parse_label(raw_lines: list[str], cert_lines: list[str] | None = None) -> SlabLabel:
    lines = _clean(raw_lines)
    targeted = _clean(cert_lines or [])
    grader = find_grader(lines)
    tier = find_tier(lines)
    cands = cert_candidates(lines, grader, targeted)
    if grader and not any(sure for _, sure in cands):
        # the grader word disagrees with every cert read (a logo read as "PSA" on an ACE label): the cert length wins
        wide = cert_candidates(lines, None, targeted)
        other = grader_for_cert(lines, wide[0][0]) if wide else None
        if other and other != grader and wide[0][1]:
            grader, cands = other, cert_candidates(lines, other, targeted)
            seen = False
        else:
            seen = True
    else:
        seen = grader is not None
    cert = cands[0][0] if cands else None
    grade = find_grade(lines, tier)
    if grader is None:
        grader = infer_grader(lines, tier, cert)
        if grader:
            cands = cert_candidates(lines, grader, targeted)
            cert = cands[0][0] if cands else None
    is_slab = bool((tier and (grade is not None or cert)) or (seen and cert))
    alt = tuple(c for c, _ in cands[1:3])
    return SlabLabel(grader, grade, cert, tier, seen, is_slab, bool(cert) and cands[0][1], alt)
