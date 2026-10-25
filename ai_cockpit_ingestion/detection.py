"""Whether a bronze table has data its bronze_to_silver DAG has not processed yet.

New = the table's newest record (max Timestamp) is later than the start of
the DAG's last successful bronze_to_silver task. Compared with the start,
not the end: a record written while that task was running is picked up by
the next run. No bookkeeping of our own: the hash-based delta check in the
operators keeps a repeated transformation idempotent (unchanged rows are not
written), and the input form's mode only reads records without a
BusinessTransaction.

Bronze Timestamps are naive UTC (lineage.utcnow, the Backend writes UTC as
well); Airflow's start dates are timezone-aware UTC. Both are compared as
naive UTC.
"""
from __future__ import annotations

import datetime

from sqlalchemy import Table, exists, func, select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.models import EXTRACT_TABLES, USER_INPUT_TABLE
from ai_cockpit_ingestion.sources import USER_INPUT, SourceConfig


def bronze_table(source: SourceConfig) -> Table:
    return USER_INPUT_TABLE if source.mode == USER_INPUT else EXTRACT_TABLES[source.extract_table]


def as_naive_utc(moment: datetime.datetime) -> datetime.datetime:
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def newest_record(session: Session, source: SourceConfig) -> datetime.datetime | None:
    return session.scalar(select(func.max(bronze_table(source).c.Timestamp)))


def has_data(session: Session, source: SourceConfig) -> bool:
    return bool(session.scalar(select(exists().select_from(bronze_table(source)))))


def is_new(newest: datetime.datetime | None, last_transform_start: datetime.datetime | None) -> bool:
    """Data newer than the last successful transformation's start (none yet: any data is new)."""
    if newest is None:
        return False
    return last_transform_start is None or as_naive_utc(newest) > as_naive_utc(last_transform_start)
