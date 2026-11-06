"""Whether a bronze table has data its bronze_to_silver DAG has not processed
yet, and the TransformationRun log behind it.

Every bronze_to_silver run logs itself in TransformationRun with the bronze
table's max(Timestamp) taken BEFORE it reads the data (start_run). New = the
table's newest record is later than the newest BronzeTimestamp of a
successful run of that table; no successful run yet -> new. A record written
while a run is going on is therefore picked up by the next run. Only bronze
timestamps are compared (naive UTC, lineage.utcnow / the Backend), no clocks
of different systems and no Airflow metadata. The hash-based delta check in
the operators keeps a repeated transformation idempotent.
"""
from __future__ import annotations

import datetime

from sqlalchemy import Table, exists, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.lineage import utcnow
from ai_cockpit_ingestion.models import EXTRACT_TABLES, USER_ACTION_TABLE, TransformationRun
from ai_cockpit_ingestion.sources import USER_INPUT, SourceConfig


def bronze_table(source: SourceConfig) -> Table:
    return USER_ACTION_TABLE if source.mode == USER_INPUT else EXTRACT_TABLES[source.extract_table]


def as_naive_utc(moment: datetime.datetime) -> datetime.datetime:
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def newest_record(session: Session, source: SourceConfig) -> datetime.datetime | None:
    return session.scalar(select(func.max(bronze_table(source).c.Timestamp)))


def has_data(session: Session, source: SourceConfig) -> bool:
    return bool(session.scalar(select(exists().select_from(bronze_table(source)))))


def processed_up_to(session: Session, source: SourceConfig) -> datetime.datetime | None:
    """The newest bronze Timestamp a successful run of this table had seen."""
    return session.scalar(
        select(func.max(TransformationRun.bronze_timestamp)).where(
            TransformationRun.bronze_table_name == source.extract_table, TransformationRun.status == "success"
        )
    )


def is_new(newest: datetime.datetime | None, seen: datetime.datetime | None) -> bool:
    """Data newer than what the last successful run had seen (none yet: any data is new)."""
    if newest is None:
        return False
    return seen is None or as_naive_utc(newest) > as_naive_utc(seen)


def needs_transform(session: Session, source: SourceConfig, force: bool = False) -> bool:
    """Whether a bronze_to_silver run has anything to do: new data in its table,
    or (force) any data at all."""
    if force:
        return has_data(session, source)
    return is_new(newest_record(session, source), processed_up_to(session, source))


def start_run(engine: Engine, source: SourceConfig, dag_run_id: str | None) -> int:
    """Log a running transformation, with the bronze table's newest Timestamp taken now —
    before the run reads the data. Committed at once, so the run is visible while it lasts."""
    with Session(engine) as session, session.begin():
        run = TransformationRun(
            bronze_table_name=source.extract_table, dag_run_id=dag_run_id, started_at=utcnow(),
            bronze_timestamp=newest_record(session, source), status="running",
        )
        session.add(run)
        session.flush()
        return run.id


def finish_run(
    session: Session, run_id: int, status: str, counts: dict | None = None, rows_read: int | None = None
) -> None:
    run = session.get(TransformationRun, run_id)
    run.status = status
    run.finished_at = utcnow()
    if counts is not None:
        run.rows_read = rows_read
        run.rows_inserted = counts.get("inserted")
        run.rows_updated = counts.get("updated")
        run.rows_unchanged = counts.get("unchanged")
        run.rows_deactivated = counts.get("deactivated")  # the user-action mode never deactivates
        # conflicts plus the sheet rows skipped because the UI owns their use case
        conflicts = [counts[k] for k in ("conflicts", "ui_owned") if counts.get(k) is not None]
        run.rows_conflict = sum(conflicts) if conflicts else None
