"""Unit tests for load_raw.parse_raw_key (pure function: no S3, no database)."""
from datetime import date

from load_raw import parse_raw_key


def test_data_file_is_parsed_into_partition_parts():
    key = "raw/source=elpris/zone=SE3/date=2026-09-15/response.json"
    assert parse_raw_key(key) == ("elpris", "SE3", date(2026, 9, 15), "response.json")


def test_zone_all_csv_is_parsed():
    key = "raw/source=svk_fcr/zone=ALL/date=2026-10-26/response.csv"
    assert parse_raw_key(key) == ("svk_fcr", "ALL", date(2026, 10, 26), "response.csv")


def test_meta_files_are_skipped():
    # Option C writes _meta.json and _last_attempt.json next to every data file.
    # Loading them as data would put JSON metadata where dbt expects prices.
    base = "raw/source=elpris/zone=SE3/date=2026-09-15/"
    assert parse_raw_key(base + "_meta.json") is None
    assert parse_raw_key(base + "_last_attempt.json") is None


def test_invalid_date_partition_is_skipped():
    assert parse_raw_key("raw/source=elpris/zone=SE3/date=garbage/response.json") is None


def test_folder_marker_and_wrong_layout_are_skipped():
    assert parse_raw_key("raw/source=elpris/zone=SE3/") is None
    assert parse_raw_key("processed/source=x/zone=y/date=2026-01-01/a.json") is None

import pytest

@pytest.mark.parametrize("bad", ["2026-02-30", "2026-13-01", "26-09-15", ""])
def test_impossible_or_malformed_dates_are_skipped(bad):
    assert parse_raw_key(f"raw/source=elpris/zone=SE3/date={bad}/response.json") is None