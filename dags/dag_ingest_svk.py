"""
ingest_svk: yesterday's balancing data (FCR from Mimer, mFRR from SVK Data
Service), every day at 10:00 Stockholm. (Day 2, step 2.7)

SvK publishes results for day D during the morning of D+1, so the 10:00 run
fetches delivery date = YESTERDAY (offset -1). Retries every 30 min until
~12:00 if a source is late.
"""
from datetime import timedelta

import pendulum
from airflow.sdk import dag, task

from battery_common import delivery_date_for, invoke_and_check


@dag(
    dag_id="ingest_svk",
    schedule="0 10 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="Europe/Stockholm"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 4, "retry_delay": timedelta(minutes=30)},
    tags=["ingestion", "svk", "scheduled"],
)
def ingest_svk():

    @task
    def fetch_yesterday(**context):
        d = delivery_date_for(context["logical_date"], offset_days=-1)
        return invoke_and_check(d, ["svk_fcr", "svk_mfrr"])

    fetch_yesterday()


ingest_svk()
