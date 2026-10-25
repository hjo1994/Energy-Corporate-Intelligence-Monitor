"""BronzeToSilver meta DAG: a factory that renders one DAG per bronze table.

For every entry in sources.BRONZE_TO_SILVER_SOURCES (the four sheet extracts
and the input form's UserInput_Initiatives_Extract) `build_bronze_to_silver_dag`
renders a DAG `bronze_to_silver_<key>`. Each of them checks only its own table:

- schedule "@continuous" with max_active_runs=1: one run is always open and
  the next starts as soon as it ends;
- wait_for_new_bronze, the DAG's own sensor (operators/new_bronze_sensor.py),
  checks every POKE_SECONDS whether its table has unprocessed data
  (detection.py): a sheet whose newest load is later than its
  BronzeLoadWatermark, input-form records without a BusinessTransaction.
  Reschedule mode, so it holds no worker slot between checks. After
  SENSOR_TIMEOUT without new data it is skipped (soft fail), the run ends
  green and the next one starts — no red runs, one empty run per day at most;
- bronze_to_silver then runs the BronzeToSilverOperator in the table's mode (sheet:
  snapshot upsert with soft delete, advancing the watermark in the same
  transaction; input form: incremental).

Trigger with {"force": true} to skip the check and recompute every
initiative of that table. A new bronze table only needs a SourceConfig entry,
no new DAG code.
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
from airflow.models.param import Param

from ai_cockpit_ingestion import config
from ai_cockpit_ingestion.operators.bronze_to_silver import BronzeToSilverOperator
from ai_cockpit_ingestion.operators.new_bronze_sensor import NewBronzeDataSensor
from ai_cockpit_ingestion.sources import BRONZE_TO_SILVER_SOURCES, USER_INPUT, SourceConfig

POKE_SECONDS = int(os.environ.get("AI_COCKPIT_BRONZE_POKE_SECONDS", "60"))
SENSOR_TIMEOUT = datetime.timedelta(hours=24)


def build_bronze_to_silver_dag(source: SourceConfig) -> DAG:
    with DAG(
        dag_id=f"bronze_to_silver_{source.key}",
        description=(
            f"{source.extract_table} -> Initiative (new initiatives from the input form)"
            if source.mode == USER_INPUT
            else f"{source.extract_table} -> Initiative (business unit {source.business_unit})"
        ),
        schedule="@continuous",
        start_date=datetime.datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        tags=["ai-cockpit", "input-orchestration", "silver"],
        params={
            "force": Param(
                False,
                type="boolean",
                description="Transform without waiting for new data and recompute every initiative "
                "(e.g. after a heuristic or config change).",
            )
        },
    ) as dag:

        wait_for_new_bronze = NewBronzeDataSensor(
            task_id="wait_for_new_bronze",
            source_key=source.key,
            db_path=str(config.DB_PATH),
            mode="reschedule",
            poke_interval=POKE_SECONDS,
            timeout=SENSOR_TIMEOUT.total_seconds(),
            soft_fail=True,
        )
        wait_for_new_bronze >> BronzeToSilverOperator(
            task_id="bronze_to_silver",
            source_key=source.key,
            db_path=str(config.DB_PATH),
        )
    return dag


for _source in BRONZE_TO_SILVER_SOURCES:
    # Module-level names are how Airflow discovers DAGs in a file.
    globals()[f"bronze_to_silver_{_source.key}"] = build_bronze_to_silver_dag(_source)
