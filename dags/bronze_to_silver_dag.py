"""BronzeToSilver meta DAG: generates one DAG per extract (bronze) table from
a single template.

For every entry in sources.BRONZE_TO_SILVER_SOURCES (the four sheets plus the
input form's UserInput_Initiatives_Extract), `build_bronze_to_silver_dag` renders a
DAG `bronze_to_silver_<key>` that is scheduled on the Dataset of its extract
table (emitted by the RawToBronze load task; for the user input reported by
the Backend via the Airflow REST API after every submission, plus a time-based
safety net, see USER_INPUT_FALLBACK_CRON) — so a fresh extract is turned into silver automatically,
and each source can also be re-run on its own (trigger with
{"force": true} to recompute every initiative, see BronzeToSilverOperator).
A new source sheet only needs
a new SourceConfig entry, no new DAG code.
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
from airflow.models.param import Param
from airflow.timetables.datasets import DatasetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

from ai_cockpit_ingestion import config
from ai_cockpit_ingestion.operators.bronze_to_silver import BronzeToSilverOperator
from ai_cockpit_ingestion.sources import BRONZE_TO_SILVER_SOURCES, USER_INPUT, SourceConfig

# Safety net for the input form (every minute): the Backend reports a Dataset event after every submission, but
# should that fail, the DAG still runs on this schedule. It is incremental (only records without a
# BusinessTransaction), so a run without new input reads nothing.
USER_INPUT_FALLBACK_CRON = os.environ.get("AI_COCKPIT_USER_INPUT_FALLBACK_CRON", "* * * * *")


def _schedule(source: SourceConfig):
    dataset = Dataset(source.asset_uri)
    if source.mode == USER_INPUT:
        return DatasetOrTimeSchedule(
            timetable=CronTriggerTimetable(USER_INPUT_FALLBACK_CRON, timezone="UTC"), datasets=[dataset]
        )
    return [dataset]


def build_bronze_to_silver_dag(source: SourceConfig) -> DAG:
    with DAG(
        dag_id=f"bronze_to_silver_{source.key}",
        description=(
            f"{source.extract_table} -> Initiative (new initiatives from the input form)"
            if source.mode == USER_INPUT
            else f"{source.extract_table} -> Initiative (business unit {source.business_unit})"
        ),
        schedule=_schedule(source),
        start_date=datetime.datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        tags=["ai-cockpit", "input-orchestration", "silver"],
        params={
            "force": Param(
                False,
                type="boolean",
                description="Recompute every initiative even if its source row is unchanged "
                "(e.g. after a heuristic or config change).",
            )
        },
    ) as dag:
        BronzeToSilverOperator(
            task_id="bronze_to_silver",
            source_key=source.key,
            db_path=str(config.DB_PATH),
        )
    return dag


for _source in BRONZE_TO_SILVER_SOURCES:
    # Module-level names are how Airflow discovers DAGs in a file.
    globals()[f"bronze_to_silver_{_source.key}"] = build_bronze_to_silver_dag(_source)
