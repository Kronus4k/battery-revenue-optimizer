"""
Unit tests for freshness_problems() in dags/battery_common.py (Day 4, step 3c).

The monitor DAG alerts on whatever this function returns. Two ways it can
fail silently:
  - too strict: alerts on data that isn't due yet (SvK for today) -> false
    alarms, people stop reading alerts;
  - too lenient: drops a real gap (tomorrow's elpris, an old missing day).
Each rule from the docstring is pinned by one test.
"""
from datetime import date

from battery_common import freshness_problems

TODAY = date(2026, 10, 10)
SVK = ["svk_fcr/ALL", "svk_mfrr/ALL"]
ELPRIS = ["elpris/SE1", "elpris/SE2", "elpris/SE3", "elpris/SE4"]


def test_normal_1530_state_has_no_problems():
    # At 15:30 SvK is missing for today and tomorrow: not due yet.
    gaps = {"2026-10-10": SVK, "2026-10-11": SVK}
    assert freshness_problems(gaps, TODAY) == {}


def test_missing_tomorrow_elpris_is_a_problem():
    # The 13:30 fetch (with retries to ~15:00) should have landed it.
    gaps = {"2026-10-11": SVK + ["elpris/SE3"]}
    assert freshness_problems(gaps, TODAY) == {"2026-10-11": ["elpris/SE3"]}


def test_missing_yesterday_svk_is_a_problem():
    # SvK for yesterday was due this morning (10:00, retries to ~12:00).
    gaps = {"2026-10-09": ["svk_fcr/ALL"]}
    assert freshness_problems(gaps, TODAY) == {"2026-10-09": ["svk_fcr/ALL"]}


def test_missing_today_elpris_is_a_problem():
    # Today's elpris was fetched YESTERDAY at 13:30.
    gaps = {"2026-10-10": SVK + ["elpris/SE1"]}
    assert freshness_problems(gaps, TODAY) == {"2026-10-10": ["elpris/SE1"]}


def test_old_fully_missing_day_reports_all_six():
    # Ingestion never retries a missed day on its own (case 1, Day 4):
    # a whole missing day in the lookback must surface completely.
    gaps = {"2026-10-05": ELPRIS + SVK}
    assert freshness_problems(gaps, TODAY) == {"2026-10-05": ELPRIS + SVK}


def test_no_gaps_means_no_problems():
    assert freshness_problems({}, TODAY) == {}