"""
Owner name normalization for cross-source deduplication.

Charleston County records format owners many ways:
  'SMITH, JOHN A'
  'John A. Smith'
  'Smith John A & Smith Mary B'
  'JOHN SMITH ESTATE'
  'Estate of John Smith, deceased'
  'JOHN DOE AND RICHARD ROE, AS REPRESENTATIVES OF...'
  'JOHN SMITH LLC'
  'SMITH FAMILY TRUST'

We produce a sortable key for matching across sources.
"""
import re
from typing import Optional

# Suffixes/markers we strip
NOISE_PATTERNS = [
    r"\(.*?\)",
    r"\bestate\s+of\b",
    r"\bestate\b",
    r"\bdeceased\b",
    r"\bdec'?d\b",
    r"\baka\b",
    r"\ba/?k/?a\b",
    r"\bf/?k/?a\b",
    r"\bet\s+al\b",
    r"\betux\b",
    r"\bet\s+ux\b",
    r"\bjr\.?\b", r"\bsr\.?\b",
    r"\bii\b", r"\biii\b", r"\biv\b",
    r"\band\s+all\s+persons.*$",
    r"\bas\s+representative.*$",
    r"\bas\s+trustees?\s+of.*$",
    r"\bguardian\s+ad\s+litem.*$",
    r"\bjohn\s+doe\b",
    r"\brichard\s+roe\b",
    r"\bjane\s+doe\b",
]

ENTITY_MARKERS = [
    "llc", "inc", "corp", "corporation", "incorporated", "company", "co",
    "ltd", "lp", "llp", "lllp", "trust", "tr", "association", "assoc",
    "partnership", "ptnrshp", "holdings",
]

PUNCT_RE = re.compile(r"[,.\"'&#/]")
WS_RE = re.compile(r"\s+")


def is_entity(name: str) -> bool:
    """True if the name looks like a business entity rather than an individual."""
    if not name:
        return False
    n = name.lower()
    return any(re.search(rf"\b{marker}\b", n) for marker in ENTITY_MARKERS)


def normalize_owner(raw: Optional[str]) -> str:
    """Returns a normalized lowercase owner key. Empty string if uninterpretable."""
    if not raw:
        return ""

    s = raw.lower().strip()

    # Strip noise (estate, etc.)
    for pat in NOISE_PATTERNS:
        s = re.sub(pat, "", s, flags=re.I)

    # Replace punctuation with space (keep hyphens for hyphenated last names)
    s = PUNCT_RE.sub(" ", s)
    s = WS_RE.sub(" ", s).strip()

    # If multiple owners separated by 'and'/'or', keep first only — typical format
    # 'SMITH JOHN AND SMITH MARY' → 'smith john'
    if " and " in s:
        s = s.split(" and ")[0].strip()
    if " or " in s:
        s = s.split(" or ")[0].strip()

    # Handle 'SMITH, JOHN A' → 'smith john a' (already comma-stripped, just confirm word order)
    # Handle 'John A Smith' → keep as-is

    # Collapse to alphanumeric tokens only
    tokens = [t for t in s.split() if t]
    s = " ".join(tokens)

    return s


def owner_key(raw: Optional[str]) -> str:
    """
    Returns the strongest dedup key. For individuals: 'lastname firstname-initial'.
    For entities: full normalized string.
    """
    if not raw:
        return ""
    if is_entity(raw):
        return normalize_owner(raw)

    norm = normalize_owner(raw)
    if not norm:
        return ""

    tokens = norm.split()
    if len(tokens) == 0:
        return ""
    if len(tokens) == 1:
        return tokens[0]

    # Heuristic: if first token followed by at least 2 more tokens AND first token
    # is short (likely first name), assume "FIRST [MIDDLE] LAST" order
    # Otherwise assume "LAST FIRST [MIDDLE]" (county records style)
    first = tokens[0]
    if len(first) <= 2 or len(tokens) == 2:
        # 'john smith' style — last is final token
        last = tokens[-1]
        firstname = tokens[0]
    else:
        # 'smith john a' style — last is first token
        last = tokens[0]
        firstname = tokens[1]

    return f"{last} {firstname[0]}" if firstname else last


def split_first_last(raw: Optional[str]) -> tuple[str, str]:
    """For GHL export — returns (first, last) display-cased."""
    if not raw:
        return ("", "")

    if is_entity(raw):
        return ("", raw.strip())

    # Strip noise but keep original casing for output
    cleaned = raw
    for pat in NOISE_PATTERNS:
        cleaned = re.sub(pat, "", cleaned, flags=re.I)
    cleaned = PUNCT_RE.sub(" ", cleaned)
    cleaned = WS_RE.sub(" ", cleaned).strip()

    if " and " in cleaned.lower():
        cleaned = re.split(r"\s+and\s+", cleaned, flags=re.I)[0].strip()

    tokens = cleaned.split()
    if not tokens:
        return ("", "")
    if len(tokens) == 1:
        return (tokens[0].title(), "")

    # Detect "LAST, FIRST" via original comma
    if "," in raw:
        parts = [p.strip() for p in raw.split(",")[:2]]
        if len(parts) == 2:
            return (parts[1].split()[0].title() if parts[1] else "",
                    parts[0].title())

    # Default: first token is first name, last token is last name (American order)
    return (tokens[0].title(), tokens[-1].title())
