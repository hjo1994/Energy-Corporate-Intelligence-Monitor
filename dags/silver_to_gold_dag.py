"""SilverToGold: Initiative (silver, versioned) -> AssessedInitiatives (gold).

Like the bronze_to_silver DAGs: schedule "@continuous" with max_active_runs=1,
and the DAG's own sensor wait_for_silver_changes (operators/silver_to_gold.py)
checks every POKE_SECONDS whether a use case is due — it has just become
complete (value buckets, confidence and delivery score, risk answers,
one-time and running costs all set),
one of its attributes changed (new silver version), or its runtime-based
RealizedValue was last computed before today. Reschedule mode, soft fail
after SENSOR_TIMEOUT without changes. Then silver_to_gold assesses the due
use cases (PotentialValue, RealizedValue, risk level; transforms/gold.py).

Trigger with {"force": true} to assess every complete use case again
(e.g. after a formula change).
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
from ai_cockpit_ingestion.operators.silver_to_gold import SilverChangesSensor, SilverToGoldOperator

POKE_SECONDS = int(os.environ.get("AI_COCKPIT_SILVER_POKE_SECONDS", "60"))
SENSOR_TIMEOUT = datetime.timedelta(hours=24)

with DAG(
    dag_id="silver_to_gold",
    description="Initiative -> AssessedInitiatives (potential value, realized value, risk level)",
    schedule="@continuous",
    start_date=datetime.datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ai-cockpit", "input-orchestration", "gold"],
    params={
        "force": Param(
            False,
            type="boolean",
            description="Assess every complete use case again without waiting for changes.",
        )
    },
) as silver_to_gold:
    wait_for_silver_changes = SilverChangesSensor(
        task_id="wait_for_silver_changes",
        db_path=str(config.DB_PATH),
        mode="reschedule",
        poke_interval=POKE_SECONDS,
        timeout=SENSOR_TIMEOUT.total_seconds(),
        soft_fail=True,
    )
    wait_for_silver_changes >> SilverToGoldOperator(task_id="silver_to_gold", db_path=str(config.DB_PATH))
