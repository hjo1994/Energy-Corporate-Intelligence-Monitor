"""Helpers for the append-only extract tables."""
from __future__ import annotations

import datetime

from sqlalchemy import Table, func, select


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def latest_load_filter(table: Table):
    """WHERE clause for the records of the most recent load of an extract
    table (all records of one load share the same Timestamp)."""
    return table.c.Timestamp == select(func.max(table.c.Timestamp)).scalar_subquery()
