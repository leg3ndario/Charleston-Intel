"""
Pure-function tests for normalizers and scoring.
These run without any network or DB.
"""
import pytest

from normalizers.address import (
    normalize_address,
    extract_zip,
    extract_state,
    is_out_of_state,
    is_absentee,
)
from normalizers.owner import normalize_owner, owner_key, split_first_last, is_entity
from db.scoring import compute_score, merge_flags


# ---------- address ----------
class TestAddress:
    def test_normalize_basic(self):
        assert normalize_address("102 Lockshire Court, Charleston, SC 29412") == "102 lockshire ct charleston 29412"

    def test_normalize_handles_uppercase(self):
        assert normalize_address("500 KING ST.") == "500 king st"

    def test_normalize_strips_units(self):
        assert "apt 4b" not in normalize_address("123 Main St Apt 4B")

    def test_normalize_directionals(self):
        assert normalize_address("123 North Main Street") == "123 n main st"

    def test_normalize_empty(self):
        assert normalize_address("") == ""
        assert normalize_address(None) == ""

    def test_extract_zip(self):
        assert extract_zip("123 Main St, Charleston, SC 29412") == "29412"
        assert extract_zip("Charleston 29412-1234") == "29412"
        assert extract_zip("no zip here") is None

    def test_extract_state(self):
        assert extract_state("123 Main St, Atlanta, GA 30301") == "GA"
        assert extract_state("123 Main St, Charleston, SC 29412") == "SC"
        assert extract_state("123 Main St, Charleston, South Carolina") == "SC"

    def test_out_of_state(self):
        assert is_out_of_state("123 Main St, Atlanta, GA 30301") is True
        assert is_out_of_state("123 Main St, Charleston, SC 29412") is False
        assert is_out_of_state(None) is False

    def test_absentee_true(self):
        assert is_absentee("102 Lockshire Ct, Charleston SC", "500 Park Ave, NYC NY") is True

    def test_absentee_false_same_address(self):
        assert is_absentee("102 Lockshire Ct, Charleston SC 29412", "102 Lockshire Court, Charleston, SC 29412") is False

    def test_absentee_handles_missing(self):
        assert is_absentee("123 Main", None) is False
        assert is_absentee(None, "123 Main") is False


# ---------- owner ----------
class TestOwner:
    def test_normalize_basic(self):
        assert "smith" in normalize_owner("John A Smith")

    def test_strip_estate(self):
        assert "estate" not in normalize_owner("Estate of John Smith, deceased")

    def test_strip_aka(self):
        result = normalize_owner("John Smith aka Johnny Smith")
        assert "aka" not in result
        # 'aka' splits — just check estate-style noise removed
        assert "smith" in result

    def test_drop_doe_roe(self):
        result = normalize_owner("Mary Jones and John Doe and Richard Roe")
        assert "doe" not in result
        assert "roe" not in result
        assert "jones" in result

    def test_entity_detection(self):
        assert is_entity("ABC Holdings LLC") is True
        assert is_entity("Smith Family Trust") is True
        assert is_entity("John Smith") is False

    def test_owner_key_individual(self):
        # "SMITH JOHN A" county style → key "smith j"
        key = owner_key("SMITH, JOHN A")
        assert key.startswith("smith")
        assert "j" in key

    def test_owner_key_entity(self):
        # Entities keep their full normalized string
        key = owner_key("ABC Holdings LLC")
        assert "abc" in key
        assert "llc" in key

    def test_owner_key_empty(self):
        assert owner_key(None) == ""
        assert owner_key("") == ""

    def test_split_first_last_simple(self):
        f, l = split_first_last("John Smith")
        assert f == "John"
        assert l == "Smith"

    def test_split_first_last_county_style(self):
        f, l = split_first_last("SMITH, JOHN A")
        assert l == "Smith"
        assert f == "John"

    def test_split_first_last_entity(self):
        f, l = split_first_last("ABC Holdings LLC")
        assert f == ""
        assert "Holdings" in l or "LLC" in l


# ---------- scoring ----------
class TestScoring:
    def test_single_flag(self):
        assert compute_score(["lis_pendens"]) == 40

    def test_two_flags_get_bonus(self):
        # 40 (lis_pendens) + 35 (tax) + 10 (multi-flag bonus for second) = 85
        assert compute_score(["lis_pendens", "tax"]) == 85

    def test_three_flags(self):
        # 40 + 35 + 30 + 10*2 = 125, capped at 100
        assert compute_score(["lis_pendens", "tax", "probate"]) == 100

    def test_caps_at_100(self):
        assert compute_score(["lis_pendens", "tax", "probate", "code", "fed_tax_lien"]) == 100

    def test_unknown_flags_ignored(self):
        assert compute_score(["banana", "nonsense"]) == 0

    def test_empty(self):
        assert compute_score([]) == 0
        assert compute_score(None) == 0

    def test_merge_flags_adds_type(self):
        flags = merge_flags("LP", [])
        assert "lis_pendens" in flags

    def test_merge_flags_adds_kwargs(self):
        flags = merge_flags("LP", [], absentee=True, out_of_state=True)
        assert "absentee" in flags
        assert "out_of_state" in flags
        assert "lis_pendens" in flags

    def test_merge_flags_dedupe(self):
        flags = merge_flags("LP", ["lis_pendens"])
        assert flags.count("lis_pendens") == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
