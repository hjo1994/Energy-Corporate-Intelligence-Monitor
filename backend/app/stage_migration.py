"""Idea and Exploration -> Ideation (11/2026) in the shared database.

The schema belongs to the input orchestration (its migration
lifecycle_2026_11._merge_ideation does the same); ensure_current_stages runs at
Backend start-up, so form 1 can store 'Ideation' even before the pipeline has
migrated the database: silver and gold (every version) get an UPDATE, and the
bronze table UserActionExtracts is rebuilt from its own CREATE statement with
the new Stage CHECK when that still lists 'Idea'. Idempotent; a read-only
database is left alone (logged).
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.schemas import FORMER_STAGES

log = logging.getLogger(__name__)

USER_ACTION_TABLE = "UserActionExtracts"
_STAGE_TABLES = ("Initiative", "AssessedInitiatives")
_FORMER_IN_CHECK = re.compile(r"'Idea',\s*'Exploration'")


def _mapped() -> str:
    cases = " ".join(f"WHEN \"Stage\" = '{old}' THEN '{new}'" for old, new in FORMER_STAGES.items())
    return f'CASE {cases} ELSE "Stage" END'


def ensure_current_stages(engine: Engine) -> None:
    former = ", ".join(f"'{stage}'" for stage in FORMER_STAGES)
    try:
        with engine.begin() as conn:
            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            for table in _STAGE_TABLES:
                if table in tables and "Stage" in {c["name"] for c in inspector.get_columns(table)}:
                    changed = conn.execute(
                        text(f'UPDATE "{table}" SET "Stage" = {_mapped()} WHERE "Stage" IN ({former})')
                    ).rowcount
                    if changed:
                        log.info("Set Stage to Ideation in %d rows of %s", changed, table)

            if USER_ACTION_TABLE not in tables:
                return
            create = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"), {"name": USER_ACTION_TABLE}
            ).scalar() or ""
            if "'Idea'" not in create:
                return
            new_create = _FORMER_IN_CHECK.sub("'Ideation'", create)
            if "'Idea'" in new_create:
                log.warning("%s: unexpected Stage CHECK, left for the pipeline's migration", USER_ACTION_TABLE)
                return
            indexes = [row[0] for row in conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = :name AND sql IS NOT NULL"),
                {"name": USER_ACTION_TABLE},
            )]
            columns = [c["name"] for c in inspector.get_columns(USER_ACTION_TABLE)]
            old = f"{USER_ACTION_TABLE}_before_ideation"
            for index in inspector.get_indexes(USER_ACTION_TABLE):
                conn.execute(text(f'DROP INDEX IF EXISTS "{index["name"]}"'))
            conn.execute(text(f'ALTER TABLE "{USER_ACTION_TABLE}" RENAME TO "{old}"'))
            conn.execute(text(new_create))
            listed = ", ".join(f'"{c}"' for c in columns)
            selected = ", ".join(_mapped() if c == "Stage" else f'"{c}"' for c in columns)
            conn.execute(text(f'INSERT INTO "{USER_ACTION_TABLE}" ({listed}) SELECT {selected} FROM "{old}" ORDER BY "ID"'))
            conn.execute(text(f'DROP TABLE "{old}"'))
            for index in indexes:
                conn.execute(text(index))
            log.info("Rebuilt %s with the stage Ideation", USER_ACTION_TABLE)
    except SQLAlchemyError as err:
        log.warning("Could not move the stages to Ideation (%s); the pipeline's migration will do it", err)
