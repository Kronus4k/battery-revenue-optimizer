"""
ingest_svk.py - Step 3: balancing-market prices from Svenska kraftnät

Two sources, because SvK is mid-migration:
  - FCR (FCR-N, FCR-D up, FCR-D down): Mimer, CSV download.
    (FCR on the new SVK Data Service stopped updating in June 2026.)
  - mFRR capacity market: SVK Data Service, JSON API (CKAN datastore_search).
    (Mimer is planned to be decommissioned, so new sources go here.)

Both files contain ALL zones, so they go under zone=ALL (Decision A):
raw stays exactly as downloaded; dbt splits zones on Day 3.

Run:
    python ingest_svk.py               # today
    python ingest_svk.py 2026-09-20    # a specific date
"""

import hashlib                                 # content hash of the mFRR rows
import json                                    # to build the mFRR filter and read the answer
import sys
from datetime import date, timedelta           # timedelta: "the next day" for mFRR's range
from urllib.parse import urlencode             # turns a dict into ?a=1&b=2, safely encoded

import requests

# Reuse the shared raw-zone rules, so every source behaves identically.
from ingest import raw_path, write_raw, record_network_error, where

# --- Config ------------------------------------------------------------------
ZONE_ALL = "ALL"                               # one file holds every zone (Decision A)

# FCR on Mimer: the "Spara som CSV" link from the FCR page.
FCR_SOURCE = "svk_fcr"
FCR_URL = "https://mimer.svk.se/PrimaryRegulation/DownloadText"
FCR_AUCTION_TYPE = 1       # 1 = "Totalt" (volume-weighted across both auction rounds)
FCR_PRODUCT_TYPE = 0       # 0 = "Samtliga" (all products: FCR-N, FCR-D up, FCR-D down)

# mFRR capacity market on SVK Data Service.
MFRR_SOURCE = "svk_mfrr"
MFRR_URL = "https://data.svk.se/api/action/datastore_search"
MFRR_RESOURCE_ID = "0c56e30d-8fce-4c27-afc8-621c230ae34d"  # from the dataset page URL
MFRR_LIMIT = 32000         # API maximum; one day is far below this, but we check anyway


# =============================================================================
# FCR from Mimer (CSV)
# =============================================================================

def build_fcr_url(delivery_date: date) -> str:
    """Mimer wants US-style dates with a time: 09/26/2026 00:00:00.
    From = To = the same day gives that one day (we verify: 24 rows)."""
    day = f"{delivery_date:%m/%d/%Y} 00:00:00"
    params = {
        "periodFrom": day,
        "periodTo": day,
        "auctionTypeId": FCR_AUCTION_TYPE,
        "productTypeId": FCR_PRODUCT_TYPE,
    }
    # urlencode escapes "/" as %2F, " " as + and ":" as %3A, so the URL is valid.
    # We build the full URL ourselves so _meta.json records exactly what we asked.
    return f"{FCR_URL}?{urlencode(params)}"


def ingest_fcr(delivery_date: date):
    url = build_fcr_url(delivery_date)
    folder = raw_path(FCR_SOURCE, ZONE_ALL, delivery_date)
    try:
        resp = requests.get(url, timeout=60)   # Mimer can be slow; allow more time
    except requests.RequestException as err:
        record_network_error(folder, url, err)
        print(f"[FCR] request failed: {err}")
        return "network_error"

    # Saved as .csv: it's CSV, and raw keeps the source's real format.
    write_raw(folder, resp, url, filename="response.csv")
    print(f"[FCR] {resp.status_code} -> {where(folder)}")
    return resp.status_code


# =============================================================================
# mFRR from SVK Data Service (JSON API)
# =============================================================================

def build_mfrr_url(delivery_date: date) -> str:
    """One local delivery day = from 00:00 this day up to (not including)
    00:00 the next day, in Swedish time, as the API guide recommends.
    On DST days this naturally returns 23 or 25 hours of rows."""
    next_day = delivery_date + timedelta(days=1)
    filters = {
        "start_time_sweden": {
            "gte": f"{delivery_date.isoformat()}T00:00:00",  # greater than or equal
            "lt": f"{next_day.isoformat()}T00:00:00",        # strictly less than
        }
    }
    params = {
        "resource_id": MFRR_RESOURCE_ID,
        # The API expects the filter as a JSON string inside the URL.
        # separators=(",", ":") drops spaces so the URL stays compact.
        "filters": json.dumps(filters, separators=(",", ":")),
        # Sort on a UNIQUE combination of columns. Each hour has 8 rows
        # (4 zones x 2 directions); sorting by time alone left their order
        # up to the database, so identical data got a different sha256.
        # time + zone + direction identifies exactly one row -> one fixed order.
        "sort": "start_time_utc asc, bidding_zone asc, reserve_direction asc",
        "limit": MFRR_LIMIT,
    }
    return f"{MFRR_URL}?{urlencode(params)}"


def records_sha256(records: list) -> str:
    """CONTENT hash: a fingerprint of the data rows only, in canonical form.
    Ignores the envelope (e.g. the 'schema' block, whose internal IDs change
    on every request), so it changes only if the DATA changes.

    Canonical = one fixed way to write the same data:
      - sort_keys=True: keys inside each row always in the same order
      - separators: no optional spaces
      - sorted(...): rows in a fixed order, whatever order the API used"""
    rows = sorted(
        json.dumps(r, sort_keys=True, separators=(",", ":")) for r in records
    )
    joined = "\n".join(rows)                   # one row per line, in fixed order
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def inspect_mfrr(resp: requests.Response) -> dict:
    """READ the raw answer to check it; never change it.
    Warns on API failure or cut-off rows. Returns extra meta fields."""
    try:
        body = resp.json()
    except ValueError:
        print("[mFRR] WARNING: answer is not valid JSON")
        return {}
    if not body.get("success", False):         # CKAN puts success: true/false in the body
        print(f"[mFRR] WARNING: API says success=false: {body.get('error')}")
        return {}
    records = body["result"]["records"]
    got, total = len(records), body["result"].get("total")
    print(f"[mFRR] rows returned: {got}, total available: {total}")
    if total is not None and got < total:
        print("[mFRR] WARNING: incomplete! More rows exist than were returned.")
    return {"row_count": got, "records_sha256": records_sha256(records)}


def ingest_mfrr(delivery_date: date):
    url = build_mfrr_url(delivery_date)
    folder = raw_path(MFRR_SOURCE, ZONE_ALL, delivery_date)
    try:
        resp = requests.get(url, timeout=60)
    except requests.RequestException as err:
        record_network_error(folder, url, err)
        print(f"[mFRR] request failed: {err}")
        return "network_error"

    # Inspect first, so the content hash can go into the meta files.
    extra = inspect_mfrr(resp) if resp.status_code == 200 else {}
    write_raw(folder, resp, url, extra=extra)  # JSON -> default response.json
    print(f"[mFRR] {resp.status_code} -> {where(folder)}")
    return resp.status_code


# =============================================================================
if __name__ == "__main__":
    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    # Each source runs independently: FCR failing never stops mFRR.
    print({"FCR": ingest_fcr(target), "mFRR": ingest_mfrr(target)})
