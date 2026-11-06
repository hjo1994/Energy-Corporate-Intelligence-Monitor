"""Idea and Exploration -> Ideation at start-up (app/stage_migration.py)."""
import sqlite3

from fastapi.testclient import TestClient

from app.main import get_app


def test_former_stages_become_ideation(db_path):
    with sqlite3.connect(db_path) as conn:
        create = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'UserActionExtracts'").fetchone()[0]
        # the pipeline's table: a Stage CHECK with the stages before 11/2026
        old = create.rstrip().rstrip(")") + ', CONSTRAINT ck_useraction_stage CHECK ("Stage" IS NULL OR "Stage" IN ' \
            "('Idea', 'Exploration', 'PoC', 'MVP', 'Implementation', 'Production', 'Retired', 'On hold', " \
            "'Cancelled', 'Unknown')))"
        conn.executescript(f"""
            DROP TABLE "UserActionExtracts";
            {old};
            CREATE INDEX "ix_useraction_usecaseid" ON "UserActionExtracts" ("UseCaseID");
            INSERT INTO "UserActionExtracts" ("ID", "Timestamp", "SourceFileID", "SubmittedBy", "ActionType",
                "UseCaseID", "Stage") VALUES (1, '2026-10-30 10:00:00', 'ui', 'jonas', 'update', 1, 'Exploration');
            UPDATE "Initiative" SET "Stage" = 'Exploration' WHERE "UseCaseID" = 1;
            UPDATE "Initiative" SET "Stage" = 'Idea' WHERE "UseCaseID" = 3;
        """)
    for _ in range(2):  # idempotent
        TestClient(get_app(db_path))
        with sqlite3.connect(db_path) as conn:
            assert conn.execute('SELECT "Stage" FROM "UserActionExtracts"').fetchall() == [("Ideation",)]
            assert conn.execute(
                "SELECT DISTINCT \"Stage\" FROM \"Initiative\" WHERE \"UseCaseID\" IN (1, 3)").fetchall() == [("Ideation",)]
            sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'UserActionExtracts'").fetchone()[0]
            assert "'Idea'" not in sql and "'Ideation'" in sql
            assert conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'ix_useraction_usecaseid'").fetchone()
            try:
                conn.execute('UPDATE "UserActionExtracts" SET "Stage" = \'Idea\'')
                raise AssertionError("the new CHECK should refuse Idea")
            except sqlite3.IntegrityError:
                pass
