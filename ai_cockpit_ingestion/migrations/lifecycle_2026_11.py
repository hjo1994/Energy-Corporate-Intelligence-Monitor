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

Independently of that, Owner gets the new nullable column Email (ALTER TABLE),
and a database from an earlier build of this data model (one Stagegate +
PassedAt per use case) gets the four stage gate dates (_add_gate_dates).

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


def _add_owner_email(engine: Engine) -> None:
    """Owner.Email (new nullable column): ALTER TABLE, since create_all leaves existing tables alone."""
    inspector = inspect(engine)
    if "Owner" in inspector.get_table_names() and "Email" not in {c["name"] for c in inspector.get_columns("Owner")}:
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE "Owner" ADD COLUMN "Email" VARCHAR'))
        log.info("Added Owner.Email")


_GATE_TABLES = ("Initiative", "AssessedInitiatives")


def _add_gate_dates(engine: Engine) -> None:
    """Stagegate + PassedAt (last passed gate) -> one date per gate.

    Silver and gold get the four columns by ALTER TABLE, filled from the old pair.
    UserActionExtracts is rebuilt, because its CHECK constraints change too (the
    Stage "Retired"; no Stagegate check): renamed, created anew, copied, old dropped.
    The old columns of silver and gold stay unused (SQLite cannot drop columns)."""
    from ai_cockpit_ingestion.models import GATE_DATE_COLUMNS, USER_ACTION_TABLE, USER_ACTION_TABLE_NAME

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in _GATE_TABLES:
            if table not in tables:
                continue
            columns = {c["name"] for c in inspector.get_columns(table)}
            if "NeedsGateDate" in columns:
                continue
            for column in GATE_DATE_COLUMNS.values():
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" DATETIME'))
            if "Stagegate" in columns:
                for gate, column in GATE_DATE_COLUMNS.items():
                    conn.execute(text(f'UPDATE "{table}" SET "{column}" = "PassedAt" WHERE "Stagegate" = :gate'), {"gate": gate})
            log.info("Added the stage gate dates to %s", table)

        if USER_ACTION_TABLE_NAME in tables:
            columns = {c["name"] for c in inspector.get_columns(USER_ACTION_TABLE_NAME)}
            if "NeedsGateDate" not in columns:
                old = f"{USER_ACTION_TABLE_NAME}_before_gate_dates"
                for index in inspector.get_indexes(USER_ACTION_TABLE_NAME):
                    conn.execute(text(f'DROP INDEX IF EXISTS "{index["name"]}"'))
                conn.execute(text(f'ALTER TABLE "{USER_ACTION_TABLE_NAME}" RENAME TO "{old}"'))
                USER_ACTION_TABLE.create(conn)
                shared = [c.name for c in USER_ACTION_TABLE.columns if c.name in columns]
                listed = ", ".join(f'"{c}"' for c in shared)
                gate_columns = ", ".join(f'"{c}"' for c in GATE_DATE_COLUMNS.values())
                gate_values = ", ".join(
                    f"CASE WHEN \"Stagegate\" = '{gate}' THEN \"PassedAt\" END" if "Stagegate" in columns else "NULL"
                    for gate in GATE_DATE_COLUMNS
                )
                conn.execute(text(
                    f'INSERT INTO "{USER_ACTION_TABLE_NAME}" ({listed}, {gate_columns}) '
                    f'SELECT {listed}, {gate_values} FROM "{old}" ORDER BY "ID"'
                ))
                conn.execute(text(f'DROP TABLE "{old}"'))
                log.info("Rebuilt %s with the stage gate dates", USER_ACTION_TABLE_NAME)


def upgrade(engine: Engine) -> bool:
    """Migrate if needed; True when silver was rebuilt."""
    from ai_cockpit_ingestion.models import USER_ACTION_TABLE, USER_ACTION_TABLE_NAME, Base

    _add_owner_email(engine)
    _add_gate_dates(engine)
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
