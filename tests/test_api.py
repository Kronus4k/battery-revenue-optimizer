"""
Tests for api/app.py (Day 4, step 4f). No database needed: the web layer is
tested with a fake repo, the logic through its pure functions.
Values below are the real SE3 rows for 2026-10-09 from the warehouse.
"""
import json
from datetime import date
from decimal import Decimal

import pytest

from api.app import LABEL_A, LABEL_B, create_app, parse_params, shape_response

SE3_ROWS = [  # (strategy, revenue_eur, revenue_rank, is_winner), deliberately unsorted
    ("arbitrage", Decimal("89.51"), 4, False),
    ("fcr_n", Decimal("374.22"), 1, True),
    ("mfrr_down", Decimal("28.68"), 6, False),
    ("fcr_d_down", Decimal("113.16"), 2, False),
    ("mfrr_up", Decimal("69.25"), 5, False),
    ("fcr_d_up", Decimal("97.50"), 3, False),
]
SE3_UPPER = (96, Decimal("515.44"))
DAY = date(2026, 10, 9)


class FakeRepo:
    def __init__(self, rows=SE3_ROWS, upper=SE3_UPPER, healthy=True):
        self.rows, self.upper, self.healthy = rows, upper, healthy
        self.calls = []

    def ping(self):
        if not self.healthy:
            raise ConnectionError("warehouse down")
        return True

    def day(self, zone, day):
        self.calls.append((zone, day))
        return self.rows, self.upper

    def date_range(self, zone):
        return date(2026, 7, 1), date(2026, 10, 9)


# ------------------------------------------------------------ parse_params
def test_parse_params_normalises_zone():
    assert parse_params(" se3 ", "2026-10-09") == ("SE3", DAY)


@pytest.mark.parametrize("zone, day", [
    ("SE5", "2026-10-09"),          # not a Swedish zone
    ("SE3", "2026-02-30"),          # impossible date
    ("SE3", "09-10-2026"),          # wrong format
    ("SE3'; drop table x;--", "2026-10-09"),   # injection attempt never reaches SQL
    (None, "2026-10-09"),
    ("SE3", None),
])
def test_parse_params_rejects_bad_input(zone, day):
    with pytest.raises(ValueError):
        parse_params(zone, day)


# ------------------------------------------------------------ shape_response
def test_winner_comes_from_the_mart_flag():
    r = shape_response("SE3", DAY, SE3_ROWS, SE3_UPPER)
    assert r["recommendation"]["strategy"] == "fcr_n"
    assert r["recommendation"]["revenue_eur"] == 374.22


def test_strategies_are_listed_by_rank():
    r = shape_response("SE3", DAY, SE3_ROWS, SE3_UPPER)
    assert [s["rank"] for s in r["strategies"]] == [1, 2, 3, 4, 5, 6]


def test_headroom_is_b_over_a():
    # (515.44 - 374.22) / 374.22 = 37.74 % -> 37.7
    r = shape_response("SE3", DAY, SE3_ROWS, SE3_UPPER)
    assert r["optimiser_headroom_pct"] == 37.7


def test_locked_labels_and_never_expected_revenue():
    # Locked decision (Day 3): A and B carry these labels; "expected revenue"
    # must never appear, because this is a backtest, not a forecast.
    r = shape_response("SE3", DAY, SE3_ROWS, SE3_UPPER)
    assert r["recommendation"]["label"] == LABEL_A
    assert r["upper_bound"]["label"] == LABEL_B
    assert "expected revenue" not in json.dumps(r).lower()


def test_missing_upper_bound_is_null_not_crash():
    r = shape_response("SE3", DAY, SE3_ROWS, None)
    assert r["upper_bound"] is None and r["optimiser_headroom_pct"] is None


# ------------------------------------------------------------ HTTP layer
def client(repo):
    return create_app(repo).test_client()


def test_recommendation_200():
    resp = client(FakeRepo()).get("/recommendation?zone=SE3&date=2026-10-09")
    assert resp.status_code == 200
    assert resp.get_json()["recommendation"]["strategy"] == "fcr_n"


def test_bad_zone_is_400_and_never_queries():
    repo = FakeRepo()
    resp = client(repo).get("/recommendation?zone=SE9&date=2026-10-09")
    assert resp.status_code == 400
    assert repo.calls == []          # invalid input stopped BEFORE the database


def test_day_without_data_is_404_with_range():
    resp = client(FakeRepo(rows=[], upper=None)).get("/recommendation?zone=SE3&date=2026-10-10")
    body = resp.get_json()
    assert resp.status_code == 404
    assert body["available_to"] == "2026-10-09"


def test_health_503_when_warehouse_down():
    assert client(FakeRepo(healthy=False)).get("/health").status_code == 503
    assert client(FakeRepo()).get("/health").status_code == 200
