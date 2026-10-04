"""Input Orchestration DAG: waits for the source Excel to appear/change and
imports it into the shared (interim) SQLite database.

See repo root README for the overall three-deployment architecture and the
shared-SQLite risk/mitigation note this DAG implements (single writer,
max_active_runs=1, atomic file swap in RawToSilverOperator).
"""
from __future__ import annotations

import datetime

from airflow.sdk import DAG

from ai_cockpit_ingestion import config
from ai_cockpit_ingestion.operators.raw_to_silver import RawToSilverOperator
from ai_cockpit_ingestion.operators.source_file_sensor import SourceFileSensor

SENSOR_TASK_ID = "wait_for_source_file"

with DAG(
    dag_id="ai_initiatives_import",
    schedule="@hourly",
    start_date=datetime.datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,  # single writer — never two raw-to-silver runs overlapping
    tags=["ai-cockpit", "input-orchestration"],
) as dag:

    wait_for_source_file = SourceFileSensor(
        task_id=SENSOR_TASK_ID,
        source_dir=str(config.SOURCE_DIR),
        filename_glob=config.SOURCE_FILENAME_GLOB,
        poke_interval=60,
        timeout=60 * 60 * 6,
        mode="reschedule",  # frees the worker slot between pokes
    )

    raw_to_silver = RawToSilverOperator(
        task_id="raw_to_silver",
        db_path=str(config.DB_PATH),
        sensor_task_id=SENSOR_TASK_ID,
        sheet_name=config.SOURCE_SHEET,
    )

    wait_for_source_file >> raw_to_silver
