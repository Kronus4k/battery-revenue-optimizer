"""
Unit tests for verify_backfill.py's pure functions (no AWS calls).
"""
from datetime import date

from verify_backfill import EXPECTED, find_gaps, parse_key


def meta_keys(day, pairs=EXPECTED):
    return [f"raw/source={s}/zone={z}/date={day}/_meta.json" for s, z in pairs]


def test_parse_key_valid():
    key = "raw/source=elpris/zone=SE3/date=2026-09-25/_meta.json"
    assert parse_key(key) == ("elpris", "SE3", "2026-09-25", "_meta.json")


def test_parse_key_ignores_other_layouts():
    assert parse_key("processed/whatever.parquet") is None


def test_find_gaps_complete_range():
    keys = meta_keys("2026-09-24") + meta_keys("2026-09-25")
    assert find_gaps(keys, date(2026, 9, 24), date(2026, 9, 25)) == {}


def test_find_gaps_whole_day_missing():
    # Note 2.10: a whole missing day = no run asked for it.
    keys = meta_keys("2026-09-25")
    gaps = find_gaps(keys, date(2026, 9, 24), date(2026, 9, 25))
    assert list(gaps) == ["2026-09-24"]
    assert len(gaps["2026-09-24"]) == len(EXPECTED)


def test_find_gaps_attempt_without_data_is_a_gap():
    # Option C: _last_attempt.json alone means "tried, no data".
    keys = [k for k in meta_keys("2026-09-24") if "zone=SE3" not in k]
    keys.append("raw/source=elpris/zone=SE3/date=2026-09-24/_last_attempt.json")
    assert find_gaps(keys, date(2026, 9, 24), date(2026, 9, 24)) == {"2026-09-24": ["elpris/SE3"]}
