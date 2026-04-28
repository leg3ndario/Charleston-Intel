"""Scoring engine. Single source of truth — frontend dashboard mirrors these weights."""
from typing import Iterable

# Score weights — keep in sync with the HTML dashboard's SCORE_WEIGHTS object.
SCORE_WEIGHTS = {
    "foreclosure": 40,
    "lis_pendens": 40,
    "tax": 35,
    "probate": 30,
    "code": 25,
    "fed_tax_lien": 25,
    "state_tax_lien": 25,
    "mechanic_lien": 15,
    "out_of_state": 15,
    "absentee": 15,
    "vacant_land": 10,
    "eviction": 10,
    "multi_flag_bonus": 10,  # added per additional flag beyond the first
}

# Flag inferred from lead_type
TYPE_TO_FLAGS = {
    "LP": ["lis_pendens"],
    "TAX": ["tax"],
    "PROB": ["probate"],
    "CODE": ["code"],
    "LIEN": [],   # specific lien type set explicitly elsewhere
    "FCL": ["foreclosure"],
    "EVCT": ["eviction"],
    "OTH": [],
}


def compute_score(flags: Iterable[str]) -> int:
    """Returns 0-100 score given a list of flag strings."""
    flags = list(set(flags or []))
    score = 0
    counted = 0
    for f in flags:
        if f in SCORE_WEIGHTS:
            score += SCORE_WEIGHTS[f]
            counted += 1
    if counted > 1:
        score += SCORE_WEIGHTS["multi_flag_bonus"] * (counted - 1)
    return min(100, score)


def merge_flags(lead_type: str, existing_flags: Iterable[str], **kwargs) -> list[str]:
    """Merge type-implied flags with existing flags + optional explicit ones."""
    flags = set(existing_flags or [])
    flags.update(TYPE_TO_FLAGS.get(lead_type, []))
    if kwargs.get("absentee"):
        flags.add("absentee")
    if kwargs.get("out_of_state"):
        flags.add("out_of_state")
    if kwargs.get("vacant_land"):
        flags.add("vacant_land")
    return sorted(flags)
