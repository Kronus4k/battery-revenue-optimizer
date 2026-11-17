"""
Where ingest.put() writes (migration Phase 4, T3). No AWS calls: S3 is faked.

Rules:
  - LAKE_TARGET=s3: the bucket comes from LAKE_BUCKET, read at CALL time.
    No fallback name: a missing LAKE_BUCKET is an error, never the old bucket.
  - LAKE_TARGET=local (or unset): unchanged, files under data/raw/, and
    LAKE_BUCKET is not needed at all.
Every test runs in a temp folder, so nothing is ever written into the repo.
"""
import pytest

import ingest

PREFIX = "raw/source=elpris/zone=SE3/date=2026-09-25"


class FakeS3:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)          # LOCAL_ROOT is relative: data/ lands in tmp
    return tmp_path


@pytest.fixture
def fake_s3(monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(ingest, "_s3_client", lambda: fake)
    return fake


def test_s3_mode_writes_to_bucket_from_env(in_tmp, fake_s3, monkeypatch):
    monkeypatch.setenv("LAKE_TARGET", "s3")
    monkeypatch.setenv("LAKE_BUCKET", "unit-test-bucket")
    ingest.put(PREFIX, "_meta.json", b"{}")
    assert [c["Bucket"] for c in fake_s3.calls] == ["unit-test-bucket"]
    assert fake_s3.calls[0]["Key"] == f"{PREFIX}/_meta.json"
    assert not (in_tmp / "data").exists()           # nothing written locally


def test_s3_mode_without_lake_bucket_raises(in_tmp, fake_s3, monkeypatch):
    monkeypatch.setenv("LAKE_TARGET", "s3")
    monkeypatch.delenv("LAKE_BUCKET", raising=False)
    with pytest.raises(RuntimeError, match="LAKE_BUCKET"):
        ingest.put(PREFIX, "_meta.json", b"{}")
    assert fake_s3.calls == []                      # no write to any bucket


@pytest.mark.parametrize("target", [None, "local"])
def test_local_mode_needs_no_bucket_and_no_s3(in_tmp, monkeypatch, target):
    if target is None:
        monkeypatch.delenv("LAKE_TARGET", raising=False)
    else:
        monkeypatch.setenv("LAKE_TARGET", target)
    monkeypatch.delenv("LAKE_BUCKET", raising=False)

    def no_s3():
        raise AssertionError("local mode must not create an S3 client")
    monkeypatch.setattr(ingest, "_s3_client", no_s3)

    ingest.put(PREFIX, "_meta.json", b"{}")
    assert (in_tmp / "data" / PREFIX / "_meta.json").read_bytes() == b"{}"
