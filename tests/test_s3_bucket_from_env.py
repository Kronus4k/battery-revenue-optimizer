"""
verify_backfill.py and load_raw.py read the lake bucket from LAKE_BUCKET.
No AWS calls and no database: both are faked.

Both scripts are mounted into Airflow on their own, so each has its own small
lake_bucket() helper. Rule for both: the bucket is read at call time and a
missing LAKE_BUCKET is an error, never a fallback to the old bucket.
"""
from datetime import date

import pytest

import load_raw
import verify_backfill


class FakePaginator:
    def __init__(self, pages):
        self.pages, self.kwargs = pages, None

    def paginate(self, **kwargs):
        self.kwargs = kwargs
        return iter(self.pages)


class FakeS3:
    def __init__(self, pages=()):
        self.paginator = FakePaginator(list(pages))
        self.get_calls = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self.paginator

    def get_object(self, **kwargs):
        self.get_calls.append(kwargs)
        return {"Body": FakeBody(b'{"sha256": "x"}')}


class FakeBody:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


def must_not_be_called(*_args, **_kwargs):
    raise AssertionError("must fail before any AWS or database call")


# ---------------------------------------------------------------- verify_backfill
def test_verify_backfill_lists_bucket_from_env(monkeypatch):
    fake = FakeS3(pages=[{"Contents": [{"Key": "raw/x"}]}])
    monkeypatch.setattr(verify_backfill.boto3, "client", lambda service: fake)
    monkeypatch.setenv("LAKE_BUCKET", "unit-test-bucket")
    assert list(verify_backfill.list_raw_keys()) == ["raw/x"]
    assert fake.paginator.kwargs == {"Bucket": "unit-test-bucket", "Prefix": "raw/"}


def test_verify_backfill_without_lake_bucket_raises(monkeypatch):
    monkeypatch.setattr(verify_backfill.boto3, "client", must_not_be_called)
    monkeypatch.delenv("LAKE_BUCKET", raising=False)
    with pytest.raises(RuntimeError, match="LAKE_BUCKET"):
        list(verify_backfill.list_raw_keys())


# ---------------------------------------------------------------- load_raw
def test_load_raw_list_data_keys_uses_given_bucket():
    key = "raw/source=elpris/zone=SE3/date=2026-09-15/response.json"
    fake = FakeS3(pages=[{"Contents": [{"Key": key}]}])
    found = load_raw.list_data_keys(fake, "unit-test-bucket",
                                    date(2026, 9, 15), date(2026, 9, 15))
    assert [k for k, _ in found] == [key]
    assert fake.paginator.kwargs["Bucket"] == "unit-test-bucket"


def test_load_raw_read_meta_uses_given_bucket():
    fake = FakeS3()
    meta = load_raw.read_meta(fake, "unit-test-bucket",
                              "raw/source=elpris/zone=SE3/date=2026-09-15/response.json")
    assert meta == {"sha256": "x"}
    assert fake.get_calls == [{"Bucket": "unit-test-bucket",
                               "Key": "raw/source=elpris/zone=SE3/date=2026-09-15/_meta.json"}]


class FakeConn:
    """Just enough of a psycopg2 connection for load() with zero files."""
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self

    def close(self):
        pass


def test_load_raw_load_reads_bucket_from_env(monkeypatch):
    fake = FakeS3(pages=[{"Contents": []}])
    monkeypatch.setattr(load_raw.boto3, "client", lambda service: fake)
    monkeypatch.setattr(load_raw, "connect_warehouse", lambda: FakeConn())
    monkeypatch.setenv("LAKE_BUCKET", "unit-test-bucket")
    counts = load_raw.load(date(2026, 9, 15), date(2026, 9, 15))
    assert counts == {"inserted": 0, "updated": 0, "unchanged": 0}
    assert fake.paginator.kwargs["Bucket"] == "unit-test-bucket"


def test_load_raw_without_lake_bucket_raises_before_any_call(monkeypatch):
    monkeypatch.setattr(load_raw.boto3, "client", must_not_be_called)
    monkeypatch.setattr(load_raw, "connect_warehouse", must_not_be_called)
    monkeypatch.delenv("LAKE_BUCKET", raising=False)
    with pytest.raises(RuntimeError, match="LAKE_BUCKET"):
        load_raw.load(date(2026, 9, 15), date(2026, 9, 15))
