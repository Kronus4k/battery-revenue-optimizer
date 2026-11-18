"""
ingest_daily: manual reruns and backfills only. Keep this DAG paused.

Offset 0: the logical date is the delivery date, all sources at once.
Daily unattended ingestion is done by ingest_elpris (13:30, tomorrow) and
ingest_svk (10:00, yesterday).

Backfill rule: enter explicit times in the dialog, then verify the
first and last run's logged date and run verify_backfill.py over a wider window.
"""
from datetime import timedelta

import pendulum
from airflow.sdk import dag, task

from battery_common import ALL_SOURCES, delivery_date_for, invoke_and_check


@dag(
    dag_id="ingest_daily",
    schedule="@daily",                 # needed for the Backfill option only
    start_date=pendulum.datetime(2026, 6, 1, tz="Europe/Stockholm"),
    catchup=False,
    max_active_runs=3,
    default_args={"retries": 3, "retry_delay": timedelta(minutes=10)},
    tags=["ingestion", "backfill", "manual"],
)
def ingest_daily():

    @task
    def invoke_ingest(**context):
        d = delivery_date_for(context["logical_date"], offset_days=0)
        return invoke_and_check(d, ALL_SOURCES)

    invoke_ingest()


ingest_daily()
