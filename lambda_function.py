"""
lambda_function.py - the entry point AWS Lambda calls.

Lambda doesn't run "python ingest.py". Instead it imports this file and calls
lambda_handler(event, context) each time the function is triggered.
  - event:   a dict with the input (from a test, a schedule, or Airflow later)
  - context: runtime info from AWS (time left, request id); we don't need it

Example events:
  {}                                              -> all sources, today (Stockholm)
  {"date": "2026-09-20"}                          -> all sources, that date
  {"date": "2026-09-20", "sources": ["elpris"]}   -> only spot prices

Lambda configuration this code expects (set in the console):
  LAKE_TARGET=s3
  LAKE_BUCKET=project-battery-optimizer-lake
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo          # time zones, built into Python 3.9+

import ingest                          # elpris + shared helpers
import ingest_svk                      # FCR + mFRR

STOCKHOLM = ZoneInfo("Europe/Stockholm")

# Name -> function that ingests one day. Adding a source = one line here.
SOURCES = {
    "elpris": ingest.ingest_day,
    "svk_fcr": ingest_svk.ingest_fcr,
    "svk_mfrr": ingest_svk.ingest_mfrr,
}


def today_in_stockholm() -> date:
    """Lambda's clock runs in UTC. Between 00:00 and 02:00 Swedish summer
    time, UTC is still on YESTERDAY. date.today() would silently fetch the
    wrong delivery day, so we ask for today's date in Stockholm explicitly."""
    return datetime.now(STOCKHOLM).date()


def lambda_handler(event, context):
    event = event or {}                                  # a test event can be empty

    # Which day: from the event if given, else today in Stockholm.
    if "date" in event:
        target = date.fromisoformat(event["date"])       # bad format -> clear error
    else:
        target = today_in_stockholm()

    # Which sources: from the event if given, else all of them.
    names = event.get("sources", list(SOURCES))
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        # Fail loudly on typos instead of silently skipping a source.
        raise ValueError(f"Unknown sources: {unknown}. Valid: {list(SOURCES)}")

    results = {}
    for name in names:
        # Each source runs independently; one failing never stops the others.
        # (Each ingest function already records its own failures in S3.)
        results[name] = SOURCES[name](target)

    print({"date": target.isoformat(), "results": results})  # -> CloudWatch logs
    # Whatever we return is shown in the console test, and later to Airflow.
    return {"date": target.isoformat(), "results": results}
