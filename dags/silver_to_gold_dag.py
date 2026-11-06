"""SilverToGold: Initiative (silver, versioned) -> AssessedInitiatives (gold).

Event-driven like the bronze_to_silver DAGs: triggered by the silver Dataset
that every bronze_to_silver_* run emits after writing silver, and once a day
(GOLD_DAILY_CRON, Europe/Berlin), because the runtime-based RealizedValue grows
with the days without any silver change. silver_to_gold assesses the due use
cases (due_use_cases: just complete, a new silver version, or RealizedValue
last computed before today; PotentialValue, RealizedValue, risk level;
transforms/gold.py). Nothing due -> the run writes nothing.

Retries instead of an endless run loop. Trigger by hand with {"force": true}
to assess every complete use case again (e.g. after a formula change).
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
from ai_cockpit_ingestion.operators.silver_to_gold import SilverToGoldOperator
from ai_cockpit_ingestion.sources import SILVER_ASSET_URI

GOLD_DAILY_CRON = os.environ.get("AI_COCKPIT_GOLD_DAILY_CRON", "0 3 * * *")

with DAG(
    dag_id="silver_to_gold",
    description="Initiative -> AssessedInitiatives (potential value, realized value, risk level)",
    schedule=DatasetOrTimeSchedule(
        timetable=CronTriggerTimetable(GOLD_DAILY_CRON, timezone="Europe/Berlin"),
        datasets=[Dataset(SILVER_ASSET_URI)],
    ),
    start_date=datetime.datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ai-cockpit", "input-orchestration", "gold"],
    default_args={"retries": 2, "retry_delay": datetime.timedelta(minutes=2)},
    params={
        "force": Param(
            False,
            type="boolean",
            description="Assess every complete use case again (e.g. after a formula change).",
        )
    },
) as silver_to_gold:
    SilverToGoldOperator(task_id="silver_to_gold", db_path=str(config.DB_PATH))
