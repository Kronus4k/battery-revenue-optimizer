"""
Unit tests for dags/battery_common.py (Day 2, step 2.8d).

Each test name says WHAT behaviour is protected. Several tests encode bugs or
traps found during Day 2 (see day2_interview_notes.md), so they can never
silently come back.
"""
from datetime import datetime

import pytest

from battery_common import (
    ALL_SOURCES,
    check_response,
    delivery_date_for,
    find_failures,
)

OK_RESULTS = {
    "elpris": {"SE1": 200, "SE2": 200, "SE3": 200, "SE4": 200},
    "svk_fcr": 200,
    "svk_mfrr": 200,
}


def utc(s):
    return datetime.fromisoformat(s)


# ---------------------------------------------------------------- delivery_date_for
@pytest.mark.parametrize(
    "logical_utc, offset, expected",
    [
        # Note 2.7: midnight Stockholm is 22:00 UTC the day BEFORE (summer).
        ("2026-09-26T22:00:00+00:00", 0, "2026-09-27"),
        # Winter time is UTC+1.
        ("2026-12-14T23:30:00+00:00", 0, "2026-12-15"),
        # Midday: UTC and local date agree (why the bug hides in normal tests).
        ("2026-09-27T12:00:00+00:00", 0, "2026-09-27"),
        # DST switch day (25-hour day): still the right calendar date.
        ("2026-10-25T00:00:00+00:00", 0, "2026-10-25"),
        # Publication offsets (Note 2.11).
        ("2026-09-30T11:30:00+00:00", +1, "2026-10-01"),  # elpris 13:30 -> tomorrow
        ("2026-09-30T08:00:00+00:00", -1, "2026-09-29"),  # svk 10:00 -> yesterday
        # Year rollover.
        ("2026-12-31T12:30:00+00:00", +1, "2027-01-01"),
    ],
)
def test_delivery_date_for(logical_utc, offset, expected):
    assert delivery_date_for(utc(logical_utc), offset) == expected


# ---------------------------------------------------------------- find_failures
def test_find_failures_all_ok():
    assert find_failures(OK_RESULTS) == []


def test_find_failures_reports_path_of_failed_zone():
    results = {"elpris": {"SE1": 200, "SE3": 404}}
    assert find_failures(results) == ["elpris.SE3=404"]


def test_find_failures_network_error_is_none():
    assert find_failures({"svk_fcr": None}) == ["svk_fcr=None"]


def test_find_failures_empty_nested_dict_is_failure():
    # Drill finding (Day 2, 50% mark): this used to return [] -> green with no prices.
    assert find_failures({"elpris": {}}) == ["elpris=EMPTY"]


def test_find_failures_string_200_is_not_success():
    # Type drift must fail, and the message must show it's a string.
    assert find_failures({"svk_fcr": "200"}) == ["svk_fcr='200'"]


# ---------------------------------------------------------------- check_response
def test_check_response_success():
    assert check_response(200, None, {"results": OK_RESULTS}, ALL_SOURCES) == []


def test_check_response_invoke_failed():
    assert check_response(500, None, {}, ["elpris"]) == ["invoke StatusCode=500"]


def test_check_response_lambda_crash_with_status_200():
    # The trap: StatusCode is 200 even when our code raised.
    problems = check_response(200, "Unhandled", {"errorMessage": "boom"}, ["elpris"])
    assert len(problems) == 1 and problems[0].startswith("lambda FunctionError=Unhandled")


def test_check_response_missing_source():
    body = {"results": {"svk_fcr": 200}}
    assert check_response(200, None, body, ["svk_fcr", "svk_mfrr"]) == ["svk_mfrr=MISSING"]


def test_check_response_empty_body():
    assert check_response(200, None, {}, ["elpris"]) == ["elpris=MISSING"]
