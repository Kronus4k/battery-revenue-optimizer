"""
battery_assets: the Airflow Assets our DAGs produce and consume (Day 4, D4.2).

An Asset is Airflow's name for "a piece of data a task produces". A task that
lists an Asset in `outlets` marks it UPDATED when (and only when) the task
succeeds; a DAG scheduled on that Asset then runs. Failed or skipped task ->
no update -> no downstream run (Airflow 3.0.6 docs, asset scheduling).

Why a separate module (not battery_common.py)?
  battery_common must NOT import Airflow, so CI can unit-test it with plain
  pytest. Assets need `airflow.sdk`, so they live here. Both ingest DAGs and
  the transform DAG import from this one file -> one definition, no typos.

Why names, not s3:// URIs?
  One SvK run writes TWO lake prefixes (svk_fcr and svk_mfrr), so no single
  real path describes "SvK data updated". A name says what the event means;
  the real paths are documented here instead:
    RAW_ELPRIS -> raw/source=elpris/zone=SE1..SE4/date=<d>/
    RAW_SVK    -> raw/source=svk_fcr/... and raw/source=svk_mfrr/...
"""
from airflow.sdk import Asset

RAW_ELPRIS = Asset(name="raw_elpris")   # updated by ingest_elpris (13:30)
RAW_SVK = Asset(name="raw_svk")         # updated by ingest_svk (10:00)