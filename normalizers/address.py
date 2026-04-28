"""
Address normalization for cross-source deduplication.

Charleston County data sources format addresses differently:
  '102 Lockshire Court, Columbia, 29212'
  '102 LOCKSHIRE CT'
  '102 Lockshire Ct., Charleston SC 29212'

We normalize to: '102 lockshire ct charleston 29412'
"""
import re
from typing import Optional

# USPS street-suffix abbreviations (subset most common in Charleston records)
SUFFIX_MAP = {
    "street": "st", "str": "st",
    "avenue": "ave", "av": "ave",
    "boulevard": "blvd", "bvd": "blvd",
    "drive": "dr",
    "court": "ct", "crt": "ct",
    "road": "rd",
    "lane": "ln",
    "place": "pl",
    "circle": "cir", "crl": "cir",
    "terrace": "ter", "terr": "ter",
    "highway": "hwy",
    "parkway": "pkwy", "pky": "pkwy",
    "trail": "trl",
    "square": "sq",
    "alley": "aly",
    "way": "way",
    "row": "row",
    "expressway": "expy",
    "freeway": "fwy",
    "junction": "jct",
    "loop": "loop",
    "path": "path",
    "ridge": "rdg",
    "run": "run",
    "crossing": "xing",
    "point": "pt",
    "harbor": "hbr",
    "island": "is",
    "landing": "lndg",
    "manor": "mnr",
    "meadow": "mdw",
    "mountain": "mtn",
    "pass": "pass",
    "plaza": "plz",
    "ranch": "rnch",
    "spring": "spg",
    "station": "sta",
    "valley": "vly",
    "village": "vlg",
    "view": "vw",
    "vista": "vis",
}

# Directional abbreviations
DIRECTION_MAP = {
    "north": "n", "south": "s", "east": "e", "west": "w",
    "northeast": "ne", "northwest": "nw",
    "southeast": "se", "southwest": "sw",
}

# Unit/suite indicators we drop entirely (low signal for dedup)
UNIT_PATTERNS = [
    r"\b(apt|apartment|unit|suite|ste|#|lot|bldg|building|fl|floor|rm|room)\s*[\w-]+",
]

ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
STATE_RE = re.compile(r"\b(SC|S\.?C\.?|south\s+carolina)\b", re.I)


def normalize_address(raw: Optional[str]) -> str:
    """Return a normalized lowercase address string suitable for comparison."""
    if not raw:
        return ""

    s = raw.lower().strip()

    # Strip punctuation except hyphens (preserve "5-A" type)
    s = re.sub(r"[.,]", " ", s)
    s = re.sub(r"\s+", " ", s)

    # Drop unit indicators
    for pat in UNIT_PATTERNS:
        s = re.sub(pat, "", s, flags=re.I)

    # Drop "SC" / "South Carolina"
    s = STATE_RE.sub("", s)

    # Replace street suffixes with standard abbreviations
    tokens = s.split()
    out = []
    for t in tokens:
        if t in SUFFIX_MAP:
            out.append(SUFFIX_MAP[t])
        elif t in DIRECTION_MAP:
            out.append(DIRECTION_MAP[t])
        else:
            out.append(t)
    s = " ".join(out)

    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()

    return s


def extract_zip(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    m = ZIP_RE.search(raw)
    return m.group(1) if m else None


def extract_state(raw: Optional[str]) -> Optional[str]:
    """Returns 2-letter state if found in mailing address. Used for out-of-state flag."""
    if not raw:
        return None
    # Look for ", XX " or ", XX" or ", XX 12345" pattern
    m = re.search(r",\s*([A-Z]{2})\b", raw.upper())
    if m:
        return m.group(1)
    if STATE_RE.search(raw):
        return "SC"
    return None


def is_out_of_state(mailing_address: Optional[str]) -> bool:
    state = extract_state(mailing_address)
    return state is not None and state != "SC"


def is_absentee(property_address: Optional[str], mailing_address: Optional[str]) -> bool:
    """True if mailing address differs meaningfully from property address."""
    if not property_address or not mailing_address:
        return False
    p_norm = normalize_address(property_address)
    m_norm = normalize_address(mailing_address)
    if not p_norm or not m_norm:
        return False
    # Compare first 4 tokens (number + street + suffix) — handles minor formatting diffs
    p_key = " ".join(p_norm.split()[:4])
    m_key = " ".join(m_norm.split()[:4])
    return p_key != m_key
