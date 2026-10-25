"""Sensor of one bronze_to_silver DAG: waits until its own bronze table has a
record newer than the start of the DAG's last successful bronze_to_silver
task (detection.py). With the run param force=true it succeeds at once (as
long as the table has any data).

Runs in reschedule mode: between pokes it holds no worker slot. Reads the
last successful task from the Airflow metadata database, which tasks may do
on Airflow 2.10 (not on Airflow 3, where this needs the REST API).
"""
from __future__ import annotations

import datetime

from airflow.models import TaskInstance
from airflow.sensors.base import BaseSensorOperator
from airflow.utils.session import NEW_SESSION, provide_session
from airflow.utils.state import TaskInstanceState
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.detection import has_data, is_new, newest_record
from ai_cockpit_ingestion.sources import SOURCES_BY_KEY

TRANSFORM_TASK_ID = "bronze_to_silver"


@provide_session
def last_successful_start(dag_id: str, task_id: str = TRANSFORM_TASK_ID, session=NEW_SESSION) -> datetime.datetime | None:
    return session.scalar(
        select(func.max(TaskInstance.start_date)).where(
            TaskInstance.dag_id == dag_id,
            TaskInstance.task_id == task_id,
            TaskInstance.state == TaskInstanceState.SUCCESS,
        )
    )


class NewBronzeDataSensor(BaseSensorOperator):
    template_fields = ("db_path",)

    def __init__(self, *, source_key: str, db_path: str, **kwargs):
        super().__init__(**kwargs)
        self.source_key = source_key
        self.db_path = db_path

    def poke(self, context) -> bool:
        source = SOURCES_BY_KEY[self.source_key]
        force = bool((context.get("params") or {}).get("force", False))
        engine = get_engine(self.db_path)
        try:
            with Session(engine) as session:
                if force:
                    return has_data(session, source)
                newest = newest_record(session, source)
        finally:
            engine.dispose()
        last_start = last_successful_start(self.dag_id)
        found = is_new(newest, last_start)
        self.log.info(
            "%s: newest record %s, last successful transformation started %s -> %s",
            source.extract_table, newest, last_start, "transform" if found else "wait",
        )
        return found
