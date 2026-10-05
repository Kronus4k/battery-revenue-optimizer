"""
ingest.py - shared raw-zone helpers + elpris spot prices (SE1-SE4)

Stores data exactly as received in the raw zone: local disk or S3 (Step 4).
Other ingestion scripts (e.g. ingest_svk.py) import raw_path, write_raw and
record_network_error from here, so every source follows the same rules.

Run:
    python ingest.py               # today's spot prices, to local disk
    python ingest.py 2026-09-20    # a specific date
    set LAKE_TARGET=s3             # (Windows cmd) then runs write to S3
"""

# --- Imports -----------------------------------------------------------------
import hashlib                                  # sha256 fingerprint of the raw bytes
import json                                     # to write _meta.json / _last_attempt.json
import os                                       # to read settings from environment variables
import sys                                      # to read the optional date argument
from datetime import date, datetime, timezone   # dates for paths, UTC time for meta
from pathlib import Path                        # OS-independent file paths

import requests                                 # HTTP client (pip install requests)

# --- Config: constants at the top so they're easy to find and change -------
SOURCE = "elpris"                               # name of the source, goes into the path
ZONES = ["SE1", "SE2", "SE3", "SE4"]            # all four Swedish bidding zones
BASE_URL = "https://www.elprisetjustnu.se/api/v1/prices"

# --- Where the lake lives: a SETTING, not hard-coded ------------------------
# Environment variables are settings given to a program from outside, so the
# same code can run locally, in Lambda, or in CI without being edited.
#   LAKE_TARGET=local (default) -> files under data/raw/... on your disk
#   LAKE_TARGET=s3              -> objects under raw/... in the S3 bucket
LAKE_TARGET = os.environ.get("LAKE_TARGET", "local")
LAKE_BUCKET = os.environ.get("LAKE_BUCKET", "project-battery-optimizer-lake")
LOCAL_ROOT = Path("data")                       # local lake root: data/raw/...

# Content types tell S3 (and browsers) what a file is.
CONTENT_TYPES = {".json": "application/json", ".csv": "text/csv"}

_s3 = None                                      # S3 client, created on first use


def _s3_client():
    """Create the boto3 S3 client once and reuse it (creating one is slow).
    boto3 finds your keys in C:/Users/<you>/.aws/credentials locally,
    and uses the Lambda's role automatically in AWS. No keys in code."""
    global _s3
    if _s3 is None:
        import boto3                            # imported here: local runs don't need it
        _s3 = boto3.client("s3")
    return _s3


def put(prefix: str, filename: str, body: bytes) -> None:
    """Write one file to the lake, wherever the lake is.
    This is the ONLY function that knows about disk vs S3."""
    key = f"{prefix}/{filename}"                # e.g. raw/source=elpris/.../_meta.json
    if LAKE_TARGET == "s3":
        # S3 has no real folders: the "path" is just part of the object's name
        # (its key). So there's nothing like mkdir; we simply write the object.
        # Writing to an existing key replaces it -> idempotency still holds.
        _s3_client().put_object(
            Bucket=LAKE_BUCKET,
            Key=key,
            Body=body,
            ContentType=CONTENT_TYPES.get(Path(filename).suffix, "application/octet-stream"),
        )
    else:
        path = LOCAL_ROOT / key
        path.parent.mkdir(parents=True, exist_ok=True)  # disk DOES need folders
        path.write_bytes(body)


def where(prefix: str) -> str:
    """Human-readable location for log lines."""
    if LAKE_TARGET == "s3":
        return f"s3://{LAKE_BUCKET}/{prefix}"
    return str(LOCAL_ROOT / prefix)


# =============================================================================
# Shared raw-zone helpers (used by every source)
# =============================================================================

def raw_path(source: str, zone: str, delivery_date: date) -> str:
    """Location (prefix) for one source/zone/day. Same inputs -> same prefix,
    always. That determinism is what makes reruns safe (idempotent).
    A plain string with "/" works for both S3 keys and local paths."""
    return (
        "raw"
        f"/source={source}"                     # Hive-style key=value partitions:
        f"/zone={zone}"                         # Athena/Spark/Databricks read these
        f"/date={delivery_date.isoformat()}"    # as columns automatically
    )


def write_raw(folder: str, resp: requests.Response, url: str,
              filename: str = "response.json", extra: dict = None) -> None:
    """Option C (Step 2):
    - the response file + _meta.json are written TOGETHER, only on success,
      so _meta.json always describes the data file next to it.
    - _last_attempt.json is written on EVERY attempt, success or failure.
    `filename` lets each source keep its real format (json, csv, ...).
    `extra` lets a source add its own fields (e.g. records_sha256 for mFRR)."""
    # One record describes this attempt; both files are built from it.
    record = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "url": url,                              # resp.url would include encoded params too
        "http_status": resp.status_code,
        "sha256": hashlib.sha256(resp.content).hexdigest(),  # BYTE hash: exactly what arrived
        "file": filename,                        # which data file this describes
    }
    record.update(extra or {})                   # add source-specific fields, if any

    meta_bytes = json.dumps(record, indent=2).encode("utf-8")  # text -> bytes for put()

    if resp.status_code == 200:
        # Exact bytes from the wire. Never parse and re-dump raw data.
        # Data first, then its label: if we crash in between, there's data
        # with an OLD label, never a label pointing at missing data.
        put(folder, filename, resp.content)
        put(folder, "_meta.json", meta_bytes)

    # Always written, outside the if: the trace of this attempt.
    put(folder, "_last_attempt.json", meta_bytes)


def record_network_error(folder: str, url: str, err: Exception) -> None:
    """No HTTP answer at all (DNS, timeout, no internet). Nothing to store,
    but the attempt is recorded. Data and _meta.json are NOT touched."""
    record = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "http_status": None,        # None -> null in JSON: no answer came back
        "sha256": None,             # nothing to fingerprint
        "error": str(err),          # the reason, as readable text
    }
    put(folder, "_last_attempt.json", json.dumps(record, indent=2).encode("utf-8"))


# =============================================================================
# Source: elpris spot prices, one file per zone per day
# =============================================================================

def build_url(zone: str, delivery_date: date) -> str:
    """e.g. .../prices/2026/09-25_SE3.json (%m and %d are zero-padded)"""
    return f"{BASE_URL}/{delivery_date:%Y}/{delivery_date:%m-%d}_{zone}.json"


def ingest_day(delivery_date: date) -> dict:
    """Fetch and store all zones for one day. Returns {zone: status}."""
    results = {}
    for zone in ZONES:
        url = build_url(zone, delivery_date)
        folder = raw_path(SOURCE, zone, delivery_date)
        try:
            resp = requests.get(url, timeout=30)  # timeout: never hang forever
        except requests.RequestException as err:
            record_network_error(folder, url, err)
            print(f"[{zone}] request failed: {err}")
            results[zone] = "network_error"
            continue                               # one bad zone never stops the rest

        write_raw(folder, resp, url)
        results[zone] = resp.status_code
        print(f"[{zone}] {resp.status_code} -> {where(folder)}")
    return results


# Runs only when executed directly, not when imported by another script.
if __name__ == "__main__":
    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    print(ingest_day(target))
