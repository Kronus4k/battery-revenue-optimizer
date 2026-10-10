"""
verify_backfill.py: does the lake actually contain what 90 green runs claim?
(Day 2, step 2.5b)

Green in Airflow = every invoke returned 200s. This script checks the other
side independently: for every delivery date in the range, does each expected
source/zone folder contain a _meta.json? (_meta.json is only written together
with the data file, Option C from Day 1, so its presence = data landed.)

Runs on your laptop (any identity that can list raw/*) and, since Day 4, inside
Airflow: the monitor_freshness DAG imports find_gaps/list_raw_keys and runs
with the airflow-local-invoker key. That key CAN list raw/* since Day 3
(read-raw-zone policy: s3:ListBucket with prefix raw/*, s3:GetObject on raw/*).
Day 2 text said it couldn't; that was true before read-raw-zone was added.

Usage (cmd, venv active):
    python verify_backfill.py 2026-07-01 2026-09-28
"""
import sys
from collections import defaultdict
from datetime import date, timedelta

import boto3

BUCKET = "project-battery-optimizer-lake"

# What every delivery date must have. 4 elpris zones + 2 SvK sources = 6.
EXPECTED = [
    ("elpris", "SE1"), ("elpris", "SE2"), ("elpris", "SE3"), ("elpris", "SE4"),
    ("svk_fcr", "ALL"),
    ("svk_mfrr", "ALL"),
]


def parse_key(key):
    """
    'raw/source=elpris/zone=SE3/date=2026-09-25/_meta.json'
      -> ('elpris', 'SE3', '2026-09-25', '_meta.json')
    Returns None for keys that don't follow the raw layout.
    """
    parts = key.split("/")
    if len(parts) != 5 or parts[0] != "raw":
        return None
    try:
        source = parts[1].split("=", 1)[1]
        zone = parts[2].split("=", 1)[1]
        day = parts[3].split("=", 1)[1]
    except IndexError:
        return None
    return source, zone, day, parts[4]


def date_range(start, end):
    d = start
    while d <= end:
        yield d.isoformat()
        d += timedelta(days=1)


def find_gaps(keys, start, end):
    """
    Pure function (no AWS), so it's easy to unit-test later in CI.
    Returns {date: [missing 'source/zone', ...]} for dates with gaps.
    """
    present = defaultdict(set)              # date -> {(source, zone), ...}
    for key in keys:
        parsed = parse_key(key)
        if parsed and parsed[3] == "_meta.json":
            source, zone, day, _ = parsed
            present[day].add((source, zone))

    gaps = {}
    for day in date_range(start, end):
        missing = [f"{s}/{z}" for s, z in EXPECTED if (s, z) not in present[day]]
        if missing:
            gaps[day] = missing
    return gaps


def list_raw_keys():
    """All keys under raw/. A paginator is needed: S3 returns max 1000 per call,
    and 90 days x 6 folders x 3 files = ~1,600 keys."""
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix="raw/"):
        for obj in page.get("Contents", []):
            yield obj["Key"]


def main():
    if len(sys.argv) != 3:
        print("Usage: python verify_backfill.py YYYY-MM-DD YYYY-MM-DD")
        sys.exit(2)
    start = date.fromisoformat(sys.argv[1])
    end = date.fromisoformat(sys.argv[2])
    n_days = (end - start).days + 1

    keys = list(list_raw_keys())
    gaps = find_gaps(keys, start, end)

    expected_total = n_days * len(EXPECTED)
    missing_total = sum(len(m) for m in gaps.values())
    print(f"Range {start} -> {end}: {n_days} days x {len(EXPECTED)} = {expected_total} expected")
    print(f"Present: {expected_total - missing_total}   Missing: {missing_total}")

    for day, missing in sorted(gaps.items()):
        print(f"  {day}: missing {', '.join(missing)}")

    # Exit code 1 on gaps -> usable later as an automated check (CI / Airflow).
    sys.exit(1 if gaps else 0)


if __name__ == "__main__":
    main()
