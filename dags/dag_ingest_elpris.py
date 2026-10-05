"""
ingest_elpris: tomorrow's day-ahead spot prices, every day at 13:30 Stockholm.
(Day 2, step 2.7)

Nord Pool publishes day-ahead prices ~13:00. elprisetjustnu.se mirrors them
shortly after, so at 13:30 we fetch delivery date = TOMORROW (offset +1).
If they're late, the source returns an error -> task fails -> retries every
15 min until ~15:00. A freshness alert at 14:00 comes on Day 3.
"""
from datetime import timedelta

import pendulum
from airflow.sdk import dag, task

from battery_common import delivery_date_for, invoke_and_check


@dag(
    dag_id="ingest_elpris",
    # Cron in the DAG's timezone (from start_date): 13:30 Stockholm all year,
    # DST included. A plain UTC cron would drift by an hour twice a year.
    schedule="30 13 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="Europe/Stockholm"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 6, "retry_delay": timedelta(minutes=15)},
    tags=["ingestion", "elpris", "scheduled"],
)
def ingest_elpris():

    @task
    def fetch_tomorrow(**context):
        d = delivery_date_for(context["logical_date"], offset_days=+1)
        return invoke_and_check(d, ["elpris"])

    fetch_tomorrow()


ingest_elpris()
