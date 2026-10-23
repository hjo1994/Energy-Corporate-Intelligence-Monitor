"""Engine factory for the shared (interim) SQLite database.

Several DAGs write to this one file now (RawToBronze plus one generated
BronzeToSilver DAG per source), so the old "build a fresh file and rename it
into place" approach no longer works. Instead every task writes in a single
short transaction: readers (Backend) keep seeing the previous committed
state until the commit, and concurrent writers wait on the SQLite lock via
busy_timeout instead of failing.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from ai_cockpit_ingestion.models import Base

BUSY_TIMEOUT_SECONDS = 120


def get_engine(db_path: str | Path) -> Engine:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"timeout": BUSY_TIMEOUT_SECONDS},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Idempotent: creates whatever tables of the data model are missing.
    Base.metadata.create_all(engine)
    return engine
