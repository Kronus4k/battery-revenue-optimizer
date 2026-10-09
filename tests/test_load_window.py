"""
Unit tests for load_window() in dags/battery_common.py (Day 4, step 2m).

load_window decides WHICH delivery dates the transform DAG reloads.
A wrong window fails silently: the run is green, but late files are never
loaded (window too short) or tomorrow's elpris prices are missed (no lookahead).
So the known answers are pinned here, including calendar edges.
"""
from datetime import date

import pytest

from battery_common import load_window


def test_default_window_is_three_back_one_ahead():
    # The real run on 2026-10-09 loaded 2026-10-06 -> 2026-10-10 (Airflow log).
    assert load_window(date(2026, 10, 9)) == ("2026-10-06", "2026-10-10")


def test_window_crosses_month_boundary():
    # 2026 is not a leap year: Feb has 28 days.
    assert load_window(date(2026, 3, 1)) == ("2026-02-26", "2026-03-02")


def test_window_crosses_year_boundary():
    assert load_window(date(2026, 1, 1)) == ("2025-12-29", "2026-01-02")


def test_dst_day_is_just_a_date():
    # 2026-10-25 has 25 hours in Stockholm, but load_window works on calendar
    # DATES (already converted to market time by the caller), so DST cannot
    # shift the window. This pins that contract.
    assert load_window(date(2026, 10, 25)) == ("2026-10-22", "2026-10-26")


def test_zero_lookback_and_lookahead_is_a_single_day():
    assert load_window(date(2026, 10, 9), 0, 0) == ("2026-10-09", "2026-10-09")


@pytest.mark.parametrize("lookback, lookahead", [(-1, 1), (3, -1)])
def test_negative_offsets_are_rejected(lookback, lookahead):
    # A negative lookback would silently produce start > end (an empty load).
    with pytest.raises(ValueError):
        load_window(date(2026, 10, 9), lookback, lookahead)