"""
monitor_freshness: is the data that SHOULD exist by now actually there?
(Day 4, D4.3)

Why a CLOCK schedule here, when everything else is event-driven?
  Missing data creates no event. If SvK never publishes, ingest_svk fails,
  no asset event fires, transform never runs, and nothing else turns red.
  Only a check on a clock can notice "nothing happened".

Why 15:30 Stockholm?
  After the last retries: SvK retries until ~12:00, elpris until ~15:00.
  An earlier check would alarm on sources that are merely late.
  (Changed from the original 14:00 plan; D4.3.)
  NOTE: a MANUAL run before ~15:00 will report tomorrow's elpris as missing.
  That is correct for its rules, not a bug.

Two independent checks, so a failure tells you WHERE to look:
  check_lake       S3 raw zone, last 7 days + tomorrow, using the same
                   find_gaps() as verify_backfill.py and freshness_problems()
                   for "is it due yet?".   Missing here -> ingestion problem.
  check_warehouse  latest day in the marts. Lake OK but marts behind
                   -> load_raw / dbt problem (look at transform runs).

A real data problem raises AirflowFailException: the task fails at once,
WITHOUT retries (retrying won't make missing data appear). Infrastructure
errors (S3/DB unreachable) raise normal exceptions and DO get the retry.
"""
import sys
from datetime import timedelta

import pendulum
from airflow.exceptions import AirflowFailException
from airflow.sdk import dag, task

from battery_common import MARKET_TZ, freshness_problems

SCRIPTS = "/opt/airflow/scripts"   # verify_backfill.py + load_raw.py, mounted read-only
LOOKBACK_DAYS = 7                  # how far back the lake check looks for gaps


def market_today(context):
    """Market-time 'today' for this run: the scheduled slot if there is one,
    else now (manual runs). A late catch-up run still checks ITS day."""
    when = context.get("logical_date") or pendulum.now("UTC")
    return when.astimezone(MARKET_TZ).date()


def import_scripts():
    """Make the mounted scripts importable for THIS task process only
    (no global PYTHONPATH that would affect the scheduler)."""
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)


@dag(
    dag_id="monitor_freshness",
    schedule="30 15 * * *",
    start_date=pendulum.datetime(2026, 10, 1, tz="Europe/Stockholm"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["monitoring", "freshness"],
)
def monitor_freshness():

    @task
    def check_lake(**context):
        import_scripts()
        from verify_backfill import find_gaps, list_raw_keys

        today = market_today(context)
        start = today - timedelta(days=LOOKBACK_DAYS)
        end = today + timedelta(days=1)                  # tomorrow's elpris
        gaps = find_gaps(list(list_raw_keys()), start, end)
        problems = freshness_problems(gaps, today)

        print(f"Lake check {start} -> {end} (today = {today})")
        print(f"Raw gaps (incl. not-yet-due): {gaps}")
        if problems:
            lines = [f"{day}: {', '.join(m)}" for day, m in sorted(problems.items())]
            raise AirflowFailException(
                "LAKE MISSING (ingestion problem; backfill with ingest_daily):\n  "
                + "\n  ".join(lines))
        print("Lake OK: everything due by now is present.")

    @task
    def check_warehouse(**context):
        import_scripts()
        from load_raw import connect_warehouse

        today = market_today(context)
        want_strategy = today - timedelta(days=1)        # both sources for yesterday
        want_arbitrage = today + timedelta(days=1)       # spot for tomorrow (13:30)

        conn = connect_warehouse()
        try:
            with conn.cursor() as cur:
                cur.execute("select max(delivery_date) from analytics_marts.mart_strategy_daily")
                strategy_max = cur.fetchone()[0]
                cur.execute("select max(delivery_date) from analytics_marts.fct_arbitrage_daily")
                arbitrage_max = cur.fetchone()[0]
        finally:
            conn.close()

        print(f"Warehouse: strategy max {strategy_max} (want >= {want_strategy}), "
              f"arbitrage max {arbitrage_max} (want >= {want_arbitrage})")
        behind = []
        if strategy_max is None or strategy_max < want_strategy:
            behind.append(f"mart_strategy_daily max {strategy_max} < {want_strategy}")
        if arbitrage_max is None or arbitrage_max < want_arbitrage:
            behind.append(f"fct_arbitrage_daily max {arbitrage_max} < {want_arbitrage}")
        if behind:
            raise AirflowFailException(
                "WAREHOUSE BEHIND (if the lake check passed: look at transform runs):\n  "
                + "\n  ".join(behind))
        print("Warehouse OK.")

    # No dependency: both checks run, so one failure never hides the other.
    check_lake()
    check_warehouse()


monitor_freshness()
