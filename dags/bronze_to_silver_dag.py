"""BronzeToSilver meta DAG: a factory that renders one DAG per bronze table.

For every entry in sources.BRONZE_TO_SILVER_SOURCES (the four sheet extracts
and the UI's UserActionExtracts) `build_bronze_to_silver_dag` renders a DAG
`bronze_to_silver_<key>`. Event-driven, nothing runs continuously or polls:

- scheduled on the Dataset of its own bronze table (source.asset_uri). For the
  sheets raw_to_bronze emits it after each load; for UserActionExtracts the
  Backend posts a Dataset event to the Airflow REST API after every user action;
- bronze_to_silver runs the BronzeToSilverOperator in the table's mode (sheet:
  snapshot upsert with soft delete, advancing the watermark in the same
  transaction; user actions: incremental, everything not processed yet);
- silver_changed lets the run go on only when silver was written; then
  silver_updated emits the silver Dataset that triggers silver_to_gold.
  Several events while a run is going on lead to one more run, which reads
  everything new (max_active_runs=1).

Retries instead of an endless run loop: a failing run is retried twice and then
stays red until the next event. Trigger by hand with {"force": true} to
recompute every initiative of that table. A new bronze table only needs a
SourceConfig entry, no new DAG code.
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
from airflow.datasets import Dataset
from airflow.decorators import task
from airflow.models.param import Param
from airflow.operators.python import ShortCircuitOperator

from ai_cockpit_ingestion import config
from ai_cockpit_ingestion.operators.bronze_to_silver import BronzeToSilverOperator
from ai_cockpit_ingestion.sources import BRONZE_TO_SILVER_SOURCES, SILVER_ASSET_URI, USER_INPUT, SourceConfig

DEFAULT_ARGS = {"retries": 2, "retry_delay": datetime.timedelta(minutes=2)}


def wrote_silver(ti, params) -> bool:
    """True when the transform inserted, updated or deactivated a silver row (or ran with force)."""
    counts = ti.xcom_pull(task_ids="bronze_to_silver") or {}
    return bool((params or {}).get("force", False)) or any(counts.get(key) for key in ("inserted", "updated", "deactivated"))


def build_bronze_to_silver_dag(source: SourceConfig) -> DAG:
    with DAG(
        dag_id=f"bronze_to_silver_{source.key}",
        description=(
            f"{source.extract_table} -> Initiative (user actions from the UI: create, update, approve, reject)"
            if source.mode == USER_INPUT
            else f"{source.extract_table} -> Initiative (business unit {source.business_unit})"
        ),
        schedule=[Dataset(source.asset_uri)],
        start_date=datetime.datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        tags=["ai-cockpit", "input-orchestration", "silver"],
        default_args=DEFAULT_ARGS,
        params={
            "force": Param(
                False,
                type="boolean",
                description="Recompute every initiative of this table (e.g. after a heuristic or config change).",
            )
        },
    ) as dag:

        @task(task_id="silver_updated", outlets=[Dataset(SILVER_ASSET_URI)])
        def silver_updated() -> None:
            """Emits the silver Dataset (silver_to_gold)."""

        (
            BronzeToSilverOperator(task_id="bronze_to_silver", source_key=source.key, db_path=str(config.DB_PATH))
            >> ShortCircuitOperator(task_id="silver_changed", python_callable=wrote_silver)
            >> silver_updated()
        )
    return dag


for _source in BRONZE_TO_SILVER_SOURCES:
    # Module-level names are how Airflow discovers DAGs in a file.
    globals()[f"bronze_to_silver_{_source.key}"] = build_bronze_to_silver_dag(_source)
