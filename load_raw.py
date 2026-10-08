"""
load_raw.py - copy raw files from the S3 lake into the warehouse landing table.

Design (Day 3, Option A, see Note 3.x):
  * ONE row per raw data file in raw.landing_files, bytes UNTOUCHED (bytea).
  * NO parsing here. BOM, ';' separators, decimal commas, the 'Summa' row...
    all of that is fixed downstream in dbt staging, where tests can see it.
  * Idempotent: the primary key is (source, zone, delivery_date), the same
    partition as the S3 path. A rerun replaces the row; it never duplicates.
  * Honest counters: a row is only rewritten when its bytes or meta changed,
    so loaded_at shows when the data REALLY changed, not when we last ran.

Usage (cmd, from the project folder, after load_env):
    python load_raw.py 2026-07-09 2026-10-06

Credentials:
  * AWS: the standard env vars (AWS_ACCESS_KEY_ID, ...) loaded from .env.
    Locally that is the least-privilege user airflow-local-invoker
    (s3:ListBucket on raw/*, s3:GetObject on raw/*), never the admin key.
  * Warehouse: WAREHOUSE_USER / WAREHOUSE_PASSWORD / WAREHOUSE_DB from .env.
    Host/port default to the local Docker warehouse (127.0.0.1:5433);
    inside Docker (Airflow) they will be overridden to warehouse:5432.
"""

import json
import os
import sys
from datetime import date

import boto3
import psycopg2

# ---------------------------------------------------------------------------
# Configuration: everything from environment variables, with safe defaults.
# ---------------------------------------------------------------------------
BUCKET = os.environ.get("LAKE_BUCKET", "project-battery-optimizer-lake")
RAW_PREFIX = "raw/"

WAREHOUSE_HOST = os.environ.get("WAREHOUSE_HOST", "127.0.0.1")
WAREHOUSE_PORT = int(os.environ.get("WAREHOUSE_PORT", "5433"))  # NOT 5432 (Note 3.2)


# ---------------------------------------------------------------------------
# Pure function: no network, no database -> easy to unit-test.
# ---------------------------------------------------------------------------
def parse_raw_key(key):
    """
    Split a raw-zone key into its partition parts.

    'raw/source=elpris/zone=SE3/date=2026-09-15/response.json'
        -> ('elpris', 'SE3', date(2026, 9, 15), 'response.json')

    Returns None for anything that is not a DATA file:
      * meta files ('_meta.json', '_last_attempt.json') start with '_'
      * keys that don't follow the source=/zone=/date= layout
    """
    parts = key.split("/")
    # Expected: ['raw', 'source=...', 'zone=...', 'date=...', '<file>']
    if len(parts) != 5 or parts[0] != "raw":
        return None
    _, src_part, zone_part, date_part, file_name = parts
    if not (src_part.startswith("source=")
            and zone_part.startswith("zone=")
            and date_part.startswith("date=")):
        return None
    if file_name == "" or file_name.startswith("_"):
        return None  # a folder marker or a meta file, not data
    try:
        delivery_date = date.fromisoformat(date_part[len("date="):])
    except ValueError:
        return None  # e.g. 'date=garbage' -> not a valid partition
    return (src_part[len("source="):], zone_part[len("zone="):],
            delivery_date, file_name)


# ---------------------------------------------------------------------------
# S3 side
# ---------------------------------------------------------------------------
def list_data_keys(s3, start, end):
    """
    List every DATA file under raw/ whose delivery date is in [start, end].
    Uses a paginator: one ListObjectsV2 call returns at most 1000 keys,
    and our lake already holds more than that (data + 2 meta files each).
    """
    found = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=RAW_PREFIX):
        for obj in page.get("Contents", []):
            parsed = parse_raw_key(obj["Key"])
            if parsed and start <= parsed[2] <= end:
                found.append((obj["Key"], parsed))
    # Deterministic order (same rule as Day 1): sort on the unique key.
    found.sort(key=lambda item: (item[1][0], item[1][1], item[1][2]))
    return found


def read_meta(s3, data_key):
    """
    Read the _meta.json next to a data file. Option C (Day 1) writes it
    together with every data file, so a missing one is unexpected: we load
    the file anyway with meta = NULL, and a dbt test will flag it.
    """
    meta_key = data_key.rsplit("/", 1)[0] + "/_meta.json"
    try:
        body = s3.get_object(Bucket=BUCKET, Key=meta_key)["Body"].read()
    except s3.exceptions.NoSuchKey:
        return None
    return json.loads(body)


# ---------------------------------------------------------------------------
# Warehouse side
# ---------------------------------------------------------------------------
# ON CONFLICT ... DO UPDATE ... WHERE: only rewrite when something changed.
# RETURNING (xmax = 0): Postgres trick. xmax is 0 for a freshly INSERTED row
# and non-zero for an UPDATED one. If the WHERE is false (nothing changed),
# no row is returned at all -> we count it as 'unchanged'.
UPSERT_SQL = """
insert into raw.landing_files (source, zone, delivery_date, s3_key, content, meta)
values (%s, %s, %s, %s, %s, %s)
on conflict (source, zone, delivery_date) do update
   set s3_key    = excluded.s3_key,
       content   = excluded.content,
       meta      = excluded.meta,
       loaded_at = now()
 where landing_files.content is distinct from excluded.content
    or landing_files.meta    is distinct from excluded.meta
    or landing_files.s3_key  is distinct from excluded.s3_key
returning (xmax = 0) as inserted
"""


def connect_warehouse():
    return psycopg2.connect(
        host=WAREHOUSE_HOST,
        port=WAREHOUSE_PORT,
        user=os.environ["WAREHOUSE_USER"],          # KeyError = forgot load_env
        password=os.environ["WAREHOUSE_PASSWORD"],
        dbname=os.environ["WAREHOUSE_DB"],
    )


def load(start, end):
    s3 = boto3.client("s3")
    keys = list_data_keys(s3, start, end)
    print(f"Found {len(keys)} data files in S3 for {start} -> {end}")

    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    conn = connect_warehouse()
    try:
        # One transaction for the whole run: either every row lands or none.
        # 'with conn' commits on success and rolls back on any exception.
        with conn, conn.cursor() as cur:
            for key, (source, zone, delivery_date, _file) in keys:
                content = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
                meta = read_meta(s3, key)
                cur.execute(UPSERT_SQL, (
                    source, zone, delivery_date, key,
                    psycopg2.Binary(content),                 # bytes -> bytea, untouched
                    json.dumps(meta) if meta is not None else None,
                ))
                row = cur.fetchone()
                if row is None:
                    counts["unchanged"] += 1
                elif row[0]:
                    counts["inserted"] += 1
                else:
                    counts["updated"] += 1
    finally:
        conn.close()

    print(f"inserted={counts['inserted']} updated={counts['updated']} "
          f"unchanged={counts['unchanged']}")
    return counts


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python load_raw.py <start YYYY-MM-DD> <end YYYY-MM-DD>")
    load(date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2]))
