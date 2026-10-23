"""SeedConfig DAG: fills the config tables (Owner, SolutionType, ValueType,
RiskClassification) once — manual trigger only, after the first RawToBronze
run. Inserts missing entries only, never updates or deletes; see
operators/seed_config.py.
"""
from __future__ import annotations

import os
import site
import sys

current_dag_dir = os.path.dirname(os.path.abspath(__file__))

site.addsitedir(current_dag_dir)

sys.path.insert(0, '$AIRFLOW_HOME/ai_cockpit_ingestion/operators')
sys.path.insert(0, '$AIRFLOW_HOME/ai_cockpit_ingestion/transforms')
import dependency_loader  # noqa: E402,F401 — installs polars/fastexcel on the cluster if missing

import datetime

from airflow import DAG

from ai_cockpit_ingestion import config
from ai_cockpit_ingestion.operators.seed_config import SeedConfigOperator

with DAG(
    dag_id="seed_config",
    schedule=None,
    start_date=datetime.datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ai-cockpit", "input-orchestration", "config"],
) as dag:
    SeedConfigOperator(
        task_id="seed_config",
        db_path=str(config.DB_PATH),
        source_dir=str(config.SOURCE_DIR),
        filename_glob=config.SOURCE_FILENAME_GLOB,
        variables_sheet=config.VARIABLES_SHEET,
    )
