"""
load_raw --from-dir: the local reader must select exactly the files the S3 reader
selects for the same layout, because CI loads the fixtures through it.
No AWS and no database.
"""
from datetime import date

import load_raw
from test_s3_bucket_from_env import FakeS3

KEYS = [
    "raw/source=elpris/zone=SE3/date=2026-10-25/response.json",
    "raw/source=elpris/zone=SE3/date=2026-10-25/_meta.json",
    "raw/source=elpris/zone=SE3/date=2026-10-25/_last_attempt.json",
    "raw/source=svk_fcr/zone=ALL/date=2026-10-09/response.csv",
    "raw/source=svk_fcr/zone=ALL/date=2026-10-09/_meta.json",
    "raw/source=svk_mfrr/zone=ALL/date=2026-10-26/response.json",   # outside the range
    "raw/source=elpris/zone=SE3/date=garbage/response.json",        # not a partition
    "raw/notes.txt",                                                 # not the layout
]


def make_lake(root):
    for key in KEYS:
        path = root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'{"sha256": "x"}' if key.endswith("_meta.json") else b"data\r\n")


def test_local_reader_selects_the_same_files_as_s3(tmp_path):
    make_lake(tmp_path)
    start, end = date(2026, 10, 9), date(2026, 10, 25)
    local = load_raw.list_local_keys(tmp_path, start, end)
    s3 = load_raw.list_data_keys(FakeS3([{"Contents": [{"Key": k} for k in KEYS]}]),
                                 "unit-test-bucket", start, end)
    assert local == s3
    assert [key for key, _ in local] == [
        "raw/source=elpris/zone=SE3/date=2026-10-25/response.json",
        "raw/source=svk_fcr/zone=ALL/date=2026-10-09/response.csv",
    ]


def test_local_meta_is_read_and_a_missing_one_is_none(tmp_path):
    make_lake(tmp_path)
    assert load_raw.read_local_meta(
        tmp_path, "raw/source=svk_fcr/zone=ALL/date=2026-10-09/response.csv") == {"sha256": "x"}
    assert load_raw.read_local_meta(
        tmp_path, "raw/source=svk_mfrr/zone=ALL/date=2026-10-26/response.json") is None


def test_from_dir_never_touches_s3(tmp_path, monkeypatch):
    make_lake(tmp_path)
    monkeypatch.delenv("LAKE_BUCKET", raising=False)

    def must_not_be_called(*_args, **_kwargs):
        raise AssertionError("--from-dir must not create an S3 client")

    monkeypatch.setattr(load_raw.boto3, "client", must_not_be_called)
    monkeypatch.setattr(load_raw, "connect_warehouse", lambda: FakeConn())
    counts = load_raw.load(date(2026, 10, 9), date(2026, 10, 25), from_dir=tmp_path)
    assert counts == {"inserted": 2, "updated": 0, "unchanged": 0}
    # Bytes are passed through untouched, CRLF included.
    assert [row[4].adapted for row in FakeConn.rows] == [b"data\r\n", b"data\r\n"]


class FakeConn:
    rows = []

    def __init__(self):
        FakeConn.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self

    def execute(self, _sql, params):
        FakeConn.rows.append(params)

    def fetchone(self):
        return (True,)          # every row counts as inserted

    def close(self):
        pass
