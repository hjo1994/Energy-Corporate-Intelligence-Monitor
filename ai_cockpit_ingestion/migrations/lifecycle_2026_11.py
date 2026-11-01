"""Migration of an existing database to the lifecycle data model (11/2026):
user actions in bronze, versioned silver, gold.

create_all only adds missing tables, it does not change existing ones, so an
old Initiative table (unique KeyHash, RiskClassificationID, no UseCaseID)
would stay as it is. This migration:

1. drops the old Initiative table and empties BusinessTransaction and
   TransformationRun — silver is derived data and every bronze record is
   still there, so the bronze_to_silver DAGs rebuild it on their next run
   (no successful run logged -> their sensors see new data). The use cases
   get new UseCaseIDs in the process;
2. creates the new tables (create_all);
3. copies the records of the old UserInput_Initiatives_Extract into
   UserActionExtracts as ActionType 'create' (same IDs; the old table is
   kept untouched, so nothing in bronze is lost).

Idempotent: does nothing when Initiative already has a UseCaseID column, or
when there is no Initiative table yet (fresh database). Runs automatically
from db.get_engine, so the DAGs migrate the shared database on first use.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

OLD_USER_INPUT_TABLE = "UserInput_Initiatives_Extract"


def needs_migration(engine: Engine) -> bool:
    inspector = inspect(engine)
    if "Initiative" not in inspector.get_table_names():
        return False
    return "UseCaseID" not in {c["name"] for c in inspector.get_columns("Initiative")}


def upgrade(engine: Engine) -> bool:
    """Migrate if needed; True when it did."""
    from ai_cockpit_ingestion.models import USER_ACTION_TABLE, USER_ACTION_TABLE_NAME, Base

    if not needs_migration(engine):
        return False
    with engine.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        conn.execute(text('DROP TABLE "Initiative"'))
        for table in ("BusinessTransaction", "TransformationRun"):
            if table in tables:
                conn.execute(text(f'DELETE FROM "{table}"'))
        Base.metadata.create_all(conn)  # the new Initiative, UserActionExtracts, AssessedInitiatives, ...
        if OLD_USER_INPUT_TABLE in tables:
            old_columns = {c["name"] for c in inspect(conn).get_columns(OLD_USER_INPUT_TABLE)}
            shared = [c.name for c in USER_ACTION_TABLE.columns if c.name in old_columns]
            listed = ", ".join(f'"{c}"' for c in shared)
            copied = conn.execute(
                text(
                    f'INSERT INTO "{USER_ACTION_TABLE_NAME}" ({listed}, "ActionType") '
                    f"SELECT {listed}, 'create' FROM \"{OLD_USER_INPUT_TABLE}\" "
                    f'WHERE "ID" NOT IN (SELECT "ID" FROM "{USER_ACTION_TABLE_NAME}") ORDER BY "ID"'
                )
            ).rowcount
            log.info("Copied %d records from %s to %s as 'create'", copied, OLD_USER_INPUT_TABLE, USER_ACTION_TABLE_NAME)
    log.warning("Migrated to the lifecycle data model: silver was dropped and is rebuilt by the bronze_to_silver DAGs")
    return True


if __name__ == "__main__":  # python -m ai_cockpit_ingestion.migrations.lifecycle_2026_11 <db path>
    import sys

    from ai_cockpit_ingestion.db import get_engine

    logging.basicConfig(level=logging.INFO)
    get_engine(sys.argv[1]).dispose()  # get_engine runs the upgrade
