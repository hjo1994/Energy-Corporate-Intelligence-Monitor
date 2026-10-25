"""Sensor of one bronze_to_silver DAG: waits until its own bronze table has a
record newer than the newest one a successful run of that table had seen
(TransformationRun, detection.py). With the run param force=true it succeeds
at once (as long as the table has any data).

Runs in reschedule mode: between pokes it holds no worker slot. Reads only the
AI Cockpit database, nothing of Airflow's (works the same on Airflow 3).
"""
from __future__ import annotations

from airflow.sensors.base import BaseSensorOperator
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.detection import has_data, is_new, newest_record, processed_up_to
from ai_cockpit_ingestion.sources import SOURCES_BY_KEY


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
                seen = processed_up_to(session, source)
        finally:
            engine.dispose()
        found = is_new(newest, seen)
        self.log.info(
            "%s: newest record %s, last successful run had seen %s -> %s",
            source.extract_table, newest, seen, "transform" if found else "wait",
        )
        return found
