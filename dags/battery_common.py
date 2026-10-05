"""
battery_common: shared ingestion logic for all battery DAGs (Day 2, step 2.7).

Why a separate module?
  - Three DAGs (ingest_elpris, ingest_svk, ingest_daily) need the SAME checks.
    One copy means a fix (like the drill's EMPTY fix) applies everywhere.
  - Nothing here imports Airflow, so CI (step 2.8) can unit-test it with plain
    pytest, without installing Airflow. Any exception fails the Airflow task.
  - Airflow puts the dags/ folder on sys.path, so DAG files can simply
    `from battery_common import ...`.
"""
import json
from datetime import timedelta
from zoneinfo import ZoneInfo

LAMBDA_NAME = "battery-ingest"
MARKET_TZ = ZoneInfo("Europe/Stockholm")

ALL_SOURCES = ["elpris", "svk_fcr", "svk_mfrr"]


class IngestionFailed(Exception):
    """Raised when the invoke, the Lambda code, or any source failed."""


def delivery_date_for(logical_date, offset_days=0):
    """
    Logical date (UTC, from Airflow) -> delivery date string 'YYYY-MM-DD'.

    1. Convert to Stockholm time FIRST (Note 2.7: .date() on UTC shifts days).
    2. Take the local calendar date.
    3. Apply the source's publication offset:
         elpris  +1  (13:30 run fetches tomorrow's day-ahead prices)
         SvK     -1  (morning run fetches yesterday's settled data)
         backfill 0  (the logical date IS the delivery date)
    Works for datetime and pendulum (pendulum.DateTime subclasses datetime).
    """
    local_day = logical_date.astimezone(MARKET_TZ).date()
    return (local_day + timedelta(days=offset_days)).isoformat()


def find_failures(results, prefix=""):
    """
    Walk the Lambda's nested 'results' and return every entry that is not 200,
    labelled with its path, e.g. 'elpris.SE3=404'.
    Empty nested dicts count as failures ('elpris=EMPTY'), and values are shown
    with repr so the string '200' can't pass for success (Day 2 drill fixes).
    """
    failures = []
    for name, value in results.items():
        path = f"{prefix}{name}"
        if isinstance(value, dict):
            failures += find_failures(value, prefix=f"{path}.")
        elif value != 200:
            failures.append(f"{path}={value!r}")
    return failures


def check_response(status_code, function_error, body, expected_sources):
    """
    The three-layer check (Note 2.7) as a pure function -> easy to unit-test.
    Returns a list of problems; empty list = genuine success.
    """
    if status_code != 200:
        return [f"invoke StatusCode={status_code}"]
    if function_error:
        return [f"lambda FunctionError={function_error}: {body}"]

    results = body.get("results") or {}
    problems = []
    # NEW in 2.7: a requested source that is absent from the response is a
    # failure. Otherwise asking for ["svk_fcr", "svk_mfrr"] and getting back
    # only svk_fcr would pass silently.
    for source in expected_sources:
        if source not in results:
            problems.append(f"{source}=MISSING")
    problems += find_failures(results)
    return problems


def invoke_and_check(delivery_date, sources):
    """Invoke the Lambda for one delivery date and raise unless every check passes."""
    import boto3                          # imported here so unit tests don't need boto3
    from botocore.config import Config

    client = boto3.client(
        "lambda",
        config=Config(read_timeout=150, connect_timeout=10,
                      retries={"max_attempts": 0}),   # Airflow owns retries
    )
    payload = {"date": delivery_date, "sources": sources}
    print(f"Invoking {LAMBDA_NAME} with {payload}")

    response = client.invoke(
        FunctionName=LAMBDA_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )
    body = json.loads(response["Payload"].read())
    print("Lambda response:", json.dumps(body, indent=2))

    problems = check_response(response["StatusCode"], response.get("FunctionError"),
                              body, sources)
    if problems:
        raise IngestionFailed(f"{delivery_date}: {problems}")
    return {"date": delivery_date, "sources": sources}
