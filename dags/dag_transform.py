"""
transform: raw lake -> warehouse -> dbt models, triggered by DATA, not time.
(Day 4, D4.2)

Runs whenever EITHER ingest DAG successfully updates its Asset:
  ingest_svk    (10:00) -> RAW_SVK    -> transform
  ingest_elpris (13:30) -> RAW_ELPRIS -> transform
A failed fetch records no asset event, so transform never runs on missing data.

Tasks:
  load_raw   S3 raw files for a rolling window of delivery dates -> raw.landing_files
             (idempotent upsert: unchanged files are a no-op)
  dbt_build  staging -> intermediate -> marts, tests run after each model;
             a failing test SKIPS everything downstream, so the marts keep
             their last good version.

Manual runs (Trigger with config) can override the window, e.g. after a
backfill:  {"start": "2026-10-01", "end": "2026-10-05"}
"""
from datetime import timedelta

import pendulum
from airflow.sdk import Param, dag, task

from battery_assets import RAW_ELPRIS, RAW_SVK
from battery_common import MARKET_TZ, load_window

LOAD_RAW = "/opt/airflow/scripts/load_raw.py"        # mounted read-only (compose)
DBT = "/opt/dbt-venv/bin/dbt"                        # venv baked into the image (D4.1)
DBT_PROJECT = "/opt/airflow/battery_dbt"             # mounted read-only (compose)


@dag(
    dag_id="transform",
    # Asset expression: run when RAW_ELPRIS OR RAW_SVK is updated.
    schedule=(RAW_ELPRIS | RAW_SVK),
    start_date=pendulum.datetime(2026, 10, 1, tz="Europe/Stockholm"),
    catchup=False,
    max_active_runs=1,          # never two dbt builds on the same tables at once
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    params={
        # None (left empty) = use the rolling window. Set both for a manual range.
        # ["null", "string"]: the UI treats "" as missing, so None must be allowed
        # explicitly. The pattern rejects typos (e.g. 2026-1-1) BEFORE the run.
        "start": Param(None, type=["null", "string"], pattern=r"^\d{4}-\d{2}-\d{2}$",
                       description="YYYY-MM-DD, empty = rolling window"),
        "end": Param(None, type=["null", "string"], pattern=r"^\d{4}-\d{2}-\d{2}$",
                     description="YYYY-MM-DD, empty = rolling window"),
    },
    tags=["transform", "warehouse", "dbt"],
)
def transform():

    @task.bash
    def load_raw(params=None):
        # Python runs first (in Airflow) and RETURNS the shell command to run.
        start, end = params.get("start"), params.get("end")
        if not (start and end):
            # Asset-triggered runs have no logical date in Airflow 3, so the
            # window is based on "now" in market time, not UTC.
            today = pendulum.now(MARKET_TZ.key).date()
            start, end = load_window(today)
        return f"python {LOAD_RAW} {start} {end}"

    @task.bash
    def dbt_build():
        # DBT_PROFILES_DIR / DBT_TARGET_PATH / DBT_LOG_PATH come from compose.
        return f"{DBT} build --project-dir {DBT_PROJECT}"

    # Only build models after the landing table is up to date.
    load_raw() >> dbt_build()


transform()