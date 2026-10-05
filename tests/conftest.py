"""
pytest setup shared by all tests.

The DAG helpers live in dags/ (Airflow puts that folder on sys.path for DAG
files). Tests run from the project root, so we add dags/ to the path here,
the same way Airflow does. Nothing in the tested modules imports Airflow.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dags"))
sys.path.insert(0, str(ROOT))
