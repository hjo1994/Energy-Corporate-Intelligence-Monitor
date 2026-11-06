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

Independently of that, a database from an earlier build of this data model
(one Stagegate + PassedAt per use case) gets the four stage gate dates
(_add_gate_dates), every database gets the user table AppUser with the
columns pointing to it (_add_app_users), and the stages Idea and Exploration
become the one stage Ideation (_merge_ideation).

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


def _add_app_users(engine: Engine) -> None:
    """The user table (AppUser) and the columns that point to it (11/2026).

    AppUser itself comes from create_all; the new columns of existing tables
    are added by ALTER TABLE: Owner.UserID + Owner.Source ('excel' for the
    owners already there), UserActionExtracts.SubmittedByUserID,
    Initiative.CreatedByUserID / ChangedByUserID. Owner.Email (an earlier
    build) is dropped again; the signed-in user is matched through AppUser."""
    from ai_cockpit_ingestion.models import AppUser, USER_ACTION_TABLE_NAME

    AppUser.__table__.create(engine, checkfirst=True)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    new_columns = {
        "Owner": (
            ('"UserID"', 'INTEGER REFERENCES "AppUser" ("ID")'),
            ('"Source"', "VARCHAR NOT NULL DEFAULT 'excel' CHECK (\"Source\" IN ('excel', 'app'))"),
        ),
        USER_ACTION_TABLE_NAME: (('"SubmittedByUserID"', 'INTEGER REFERENCES "AppUser" ("ID")'),),
        "Initiative": (
            ('"CreatedByUserID"', 'INTEGER REFERENCES "AppUser" ("ID")'),
            ('"ChangedByUserID"', 'INTEGER REFERENCES "AppUser" ("ID")'),
        ),
    }
    with engine.begin() as conn:
        for table, columns in new_columns.items():
            if table not in tables:
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, definition in columns:
                if name.strip('"') not in existing:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {name} {definition}'))
                    log.info("Added %s.%s", table, name)
        if "Owner" in tables:
            conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS "ux_owner_userid" ON "Owner" ("UserID")'))
            if "Email" in {c["name"] for c in inspector.get_columns("Owner")}:
                conn.execute(text('ALTER TABLE "Owner" DROP COLUMN "Email"'))  # SQLite >= 3.35
                log.info("Dropped Owner.Email")


def _stage_mapped() -> str:
    """SQL for the Stage column with the former stages mapped (Idea/Exploration -> Ideation)."""
    from ai_cockpit_ingestion.models import FORMER_STAGES

    cases = " ".join(f"WHEN \"Stage\" = '{old}' THEN '{new}'" for old, new in FORMER_STAGES.items())
    return f'CASE {cases} ELSE "Stage" END'


def _selected(columns: list[str]) -> str:
    """The SELECT list for copying bronze records into the current UserActionExtracts."""
    return ", ".join(_stage_mapped() if c == "Stage" else f'"{c}"' for c in columns)


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
                    f'SELECT {_selected(shared)}, {gate_values} FROM "{old}" ORDER BY "ID"'
                ))
                conn.execute(text(f'DROP TABLE "{old}"'))
                log.info("Rebuilt %s with the stage gate dates", USER_ACTION_TABLE_NAME)


_STAGE_TABLES = ("Initiative", "AssessedInitiatives")


def _merge_ideation(engine: Engine) -> None:
    """Idea and Exploration -> Ideation (11/2026), in silver, gold and bronze.

    Silver and gold (every version) get an UPDATE. UserActionExtracts is rebuilt
    when its Stage CHECK still lists 'Idea' (renamed, created anew with the new
    CHECK, copied with the stages mapped, old dropped), like _add_gate_dates."""
    from ai_cockpit_ingestion.models import FORMER_STAGES, USER_ACTION_TABLE, USER_ACTION_TABLE_NAME

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    former = ", ".join(f"'{stage}'" for stage in FORMER_STAGES)
    mapped = _stage_mapped()
    with engine.begin() as conn:
        for table in _STAGE_TABLES:
            if table in tables and "Stage" in {c["name"] for c in inspector.get_columns(table)}:
                changed = conn.execute(text(f'UPDATE "{table}" SET "Stage" = {mapped} WHERE "Stage" IN ({former})')).rowcount
                if changed:
                    log.info("Set Stage to Ideation in %d rows of %s", changed, table)

        if USER_ACTION_TABLE_NAME not in tables:
            return
        definition = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"), {"name": USER_ACTION_TABLE_NAME}
        ).scalar() or ""
        if "'Idea'" not in definition:
            return
        old = f"{USER_ACTION_TABLE_NAME}_before_ideation"
        columns = {c["name"] for c in inspector.get_columns(USER_ACTION_TABLE_NAME)}
        for index in inspector.get_indexes(USER_ACTION_TABLE_NAME):
            conn.execute(text(f'DROP INDEX IF EXISTS "{index["name"]}"'))
        conn.execute(text(f'ALTER TABLE "{USER_ACTION_TABLE_NAME}" RENAME TO "{old}"'))
        USER_ACTION_TABLE.create(conn)
        shared = [c.name for c in USER_ACTION_TABLE.columns if c.name in columns]
        listed = ", ".join(f'"{c}"' for c in shared)
        conn.execute(text(f'INSERT INTO "{USER_ACTION_TABLE_NAME}" ({listed}) SELECT {_selected(shared)} FROM "{old}" ORDER BY "ID"'))
        conn.execute(text(f'DROP TABLE "{old}"'))
        log.info("Rebuilt %s with the stage Ideation", USER_ACTION_TABLE_NAME)


def upgrade(engine: Engine) -> bool:
    """Migrate if needed; True when silver was rebuilt."""
    from ai_cockpit_ingestion.models import USER_ACTION_TABLE, USER_ACTION_TABLE_NAME, Base

    _add_gate_dates(engine)
    _add_app_users(engine)
    _merge_ideation(engine)
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
                    f"SELECT {_selected(shared)}, 'create' FROM \"{OLD_USER_INPUT_TABLE}\" "
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
