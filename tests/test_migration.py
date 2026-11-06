"""Migration of an existing database to the lifecycle data model
(migrations.lifecycle_2026_11), against a temporary SQLite file."""
import datetime
import sqlite3

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.models import USER_ACTION_TABLE, USER_ACTION_TABLE_NAME, Initiative, Owner, ValueType
from ai_cockpit_ingestion.operators.bronze_to_silver import BronzeToSilverOperator

_OLD_USER_INPUT = {
    "Timestamp": "2026-10-25 13:00:00", "SourceFileID": "user-input", "SubmittedBy": "jonas",
    "Name": "Smart Invoice Check", "Description": "Checks invoices", "OwnerID": 1, "ValueTypeID": 1,
    "SolutionTypeID": None, "Stage": "Idea", "DateStart": None, "DateDelivery": "Q3 2027",
    "CasesPerYear": 3000, "HoursSavedPerCase": 0.5, "EstimateBasis": "benchmark", "DeliveryLikelihood": "medium",
    "SolutionComplexityScore": 4, "OneTimeCosts": 200000, "OperatingCosts": 50000,
    "EmployeePersonalData": "no", "PerformanceOrBehaviourControl": 0, "DecisionsOnEmployees": "none",
    "ProfilingOfIndividuals": 0, "ChangesEmployeeWorkflows": 1, "ProhibitedPractice": 0,
}


def _old_database(path):
    """The tables of the previous data model that the migration touches (shortened)."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE "Owner" ("ID" INTEGER PRIMARY KEY, "Category" TEXT, "Name" TEXT NOT NULL, "Department" TEXT);
        CREATE TABLE "ValueType" ("ID" INTEGER PRIMARY KEY, "Name" TEXT NOT NULL UNIQUE, "Description" TEXT);
        CREATE TABLE "BusinessTransaction" ("ID" INTEGER PRIMARY KEY, "BronzeID" INTEGER NOT NULL,
                                            "BronzeTableName" TEXT NOT NULL);
        CREATE TABLE "Initiative" ("ID" INTEGER PRIMARY KEY, "Name" TEXT NOT NULL, "KeyHash" TEXT UNIQUE,
                                   "RiskClassificationID" INTEGER NOT NULL, "BusinessTransactionID" INTEGER);
        INSERT INTO "Owner" VALUES (1, 'ETB', 'Owner A', 'Assets');
        INSERT INTO "ValueType" VALUES (1, 'CAPEX delivery', NULL);
        INSERT INTO "BusinessTransaction" VALUES (1, 1, 'UserInput_Initiatives_Extract');
        INSERT INTO "Initiative" VALUES (1, 'Smart Invoice Check', 'k', 2, 1);
    """)
    columns = ", ".join(f'"{c}" ' for c in ("ID", *_OLD_USER_INPUT))
    conn.execute(f'CREATE TABLE "UserInput_Initiatives_Extract" ({columns})')
    conn.execute(
        f'INSERT INTO "UserInput_Initiatives_Extract" VALUES ({", ".join("?" * (len(_OLD_USER_INPUT) + 1))})',
        (1, *_OLD_USER_INPUT.values()),
    )
    conn.commit()
    conn.close()


def test_old_database_is_migrated_and_silver_rebuilt(tmp_path):
    path = tmp_path / "old.db"
    _old_database(path)
    engine = get_engine(path)
    try:
        inspector = inspect(engine)
        assert {"UseCaseID", "RunningCosts", "EmployeePersonalData"} <= {
            c["name"] for c in inspector.get_columns("Initiative")}
        assert "RiskClassificationID" not in {c["name"] for c in inspector.get_columns("Initiative")}
        assert {"UserID", "Source"} <= {c["name"] for c in inspector.get_columns("Owner")}
        assert "AppUser" in inspector.get_table_names()
        assert {"AssessedInitiatives", USER_ACTION_TABLE_NAME, "UserInput_Initiatives_Extract"} <= set(
            inspector.get_table_names())
        with engine.connect() as conn:
            action = conn.execute(select(USER_ACTION_TABLE)).one()._mapping
            assert (action["ID"], action["ActionType"], action["UseCaseID"], action["Name"], action["Stage"]) == (
                1, "create", None, "Smart Invoice Check", "Ideation")  # Idea -> Ideation
            assert action["Timestamp"] == datetime.datetime(2026, 10, 25, 13, 0)

        # the DAG rebuilds silver from bronze
        op = BronzeToSilverOperator(task_id="t", source_key="user_input", db_path=str(path))
        assert op.execute({"params": {}})["inserted"] == 1
        with Session(engine) as s:
            i = s.scalars(select(Initiative)).one()
            assert (i.use_case_id, i.status, i.running_costs) == (1, "pending", 32500)
            assert s.get(Owner, 1).name == "Owner A" and s.get(ValueType, 1) is not None  # config kept
    finally:
        engine.dispose()

    # idempotent: a second start changes nothing
    engine = get_engine(path)
    with Session(engine) as s:
        assert s.query(Initiative).count() == 1
    engine.dispose()


def test_last_gate_becomes_one_date_per_gate(tmp_path):
    """A lifecycle database from before the gate dates (Stagegate + PassedAt) gets one date per gate."""
    path = tmp_path / "lifecycle.db"
    engine = get_engine(path)  # the current model
    engine.dispose()
    conn = sqlite3.connect(path)
    # back to the previous shape: the bronze table with Stagegate/PassedAt, silver with the old pair
    conn.executescript(f"""
        INSERT INTO "Owner" ("ID", "Name") VALUES (3, 'Lead');
        DROP TABLE "{USER_ACTION_TABLE_NAME}";
        CREATE TABLE "{USER_ACTION_TABLE_NAME}" ("ID" INTEGER PRIMARY KEY, "Timestamp" DATETIME NOT NULL,
            "SourceFileID" TEXT NOT NULL, "SubmittedBy" TEXT, "ActionType" TEXT NOT NULL, "UseCaseID" INTEGER,
            "Stage" TEXT, "Stagegate" TEXT, "PassedAt" DATETIME, "LeadID" INTEGER);
        INSERT INTO "{USER_ACTION_TABLE_NAME}" VALUES (1, '2026-10-30 10:00:00', 'ui', 'jonas', 'update', 7,
            'PoC', 'Scope', '2026-10-20 00:00:00', NULL);
        INSERT INTO "{USER_ACTION_TABLE_NAME}" VALUES (2, '2026-10-30 11:00:00', 'ui', 'jonas', 'approve', 8,
            NULL, 'Needs', '2026-10-30 11:00:00', 3);
        ALTER TABLE "Initiative" RENAME TO "Initiative_new";
        CREATE TABLE "Initiative" AS SELECT * FROM "Initiative_new" WHERE 0;
        DROP TABLE "Initiative_new";
    """)
    cols = [r[1] for r in conn.execute('PRAGMA table_info("Initiative")')]
    gate_cols = ("NeedsGateDate", "ScopeGateDate", "DeployGateDate", "RetireGateDate")
    kept = [c for c in cols if c not in gate_cols]
    conn.executescript(f"""
        CREATE TABLE "Initiative_old" AS SELECT {", ".join(f'"{c}"' for c in kept)} FROM "Initiative";
        DROP TABLE "Initiative";
        ALTER TABLE "Initiative_old" RENAME TO "Initiative";
        ALTER TABLE "Initiative" ADD COLUMN "Stagegate" TEXT;
        ALTER TABLE "Initiative" ADD COLUMN "PassedAt" DATETIME;
    """)
    conn.commit()
    conn.close()

    engine = get_engine(path)
    try:
        inspector = inspect(engine)
        assert set(gate_cols) <= {c["name"] for c in inspector.get_columns("Initiative")}
        bronze = {c["name"] for c in inspector.get_columns(USER_ACTION_TABLE_NAME)}
        assert set(gate_cols) <= bronze and "Stagegate" not in bronze
        with engine.connect() as c:
            rows = c.execute(select(USER_ACTION_TABLE).order_by(USER_ACTION_TABLE.c.ID)).all()
        assert [(r.ID, r.Stage, r.NeedsGateDate, r.ScopeGateDate) for r in rows] == [
            (1, "PoC", None, datetime.datetime(2026, 10, 20)),
            (2, None, datetime.datetime(2026, 10, 30, 11), None),
        ]
    finally:
        engine.dispose()

    engine = get_engine(path)  # idempotent
    with engine.connect() as c:
        assert len(c.execute(select(USER_ACTION_TABLE)).all()) == 2
    engine.dispose()


def test_user_table_and_its_columns_are_added(tmp_path):
    """A database from before the user table (Owner.Email, no user columns) gets AppUser and the user columns."""
    path = tmp_path / "before_users.db"
    get_engine(path).dispose()
    conn = sqlite3.connect(path)
    conn.executescript("""
        DROP TABLE "AppUser";
        DROP INDEX "ux_owner_userid";
        CREATE TABLE "Owner_old" ("ID" INTEGER PRIMARY KEY, "Category" VARCHAR, "Name" VARCHAR NOT NULL,
            "Department" VARCHAR, "Email" VARCHAR);
        DROP TABLE "Owner";
        ALTER TABLE "Owner_old" RENAME TO "Owner";
        INSERT INTO "Owner" ("ID", "Name", "Email") VALUES (1, 'Owner A', 'a@x.de');
    """)
    conn.commit()
    conn.close()
    for _ in range(2):  # idempotent
        engine = get_engine(path)
        inspector = inspect(engine)
        assert "AppUser" in inspector.get_table_names()
        owner_columns = {c["name"] for c in inspector.get_columns("Owner")}
        assert {"UserID", "Source"} <= owner_columns and "Email" not in owner_columns
        assert "SubmittedByUserID" in {c["name"] for c in inspector.get_columns(USER_ACTION_TABLE_NAME)}
        assert {"CreatedByUserID", "ChangedByUserID"} <= {c["name"] for c in inspector.get_columns("Initiative")}
        with Session(engine) as s:
            assert (s.get(Owner, 1).name, s.get(Owner, 1).source) == ("Owner A", "excel")
        engine.dispose()


def test_old_sqlite_keeps_owner_email(tmp_path, monkeypatch):
    """SQLite < 3.35 (the cluster) has no DROP COLUMN: Owner.Email stays, the rest of the migration runs."""
    from ai_cockpit_ingestion.migrations import lifecycle_2026_11

    monkeypatch.setattr(lifecycle_2026_11, "_supports_drop_column", lambda: False)
    path = tmp_path / "old_sqlite.db"
    get_engine(path).dispose()
    conn = sqlite3.connect(path)
    conn.executescript("""
        DROP INDEX "ux_owner_userid";
        ALTER TABLE "Owner" RENAME TO "Owner_new";
        CREATE TABLE "Owner" ("ID" INTEGER PRIMARY KEY, "Category" VARCHAR, "Name" VARCHAR NOT NULL,
            "Department" VARCHAR, "Email" VARCHAR);
        DROP TABLE "Owner_new";
        INSERT INTO "Owner" ("ID", "Name", "Email") VALUES (1, 'Owner A', 'a@x.de');
    """)
    conn.commit()
    conn.close()
    for _ in range(2):  # idempotent, no error on the second connect either
        engine = get_engine(path)
        owner_columns = {c["name"] for c in inspect(engine).get_columns("Owner")}
        assert {"UserID", "Source", "Email"} <= owner_columns
        with Session(engine) as s:
            s.add(Owner(name="Owner B", source="app"))  # new owners do not need the leftover column
            s.commit()
            assert s.get(Owner, 1).source == "excel"
        engine.dispose()


def test_idea_and_exploration_become_ideation(tmp_path):
    """A database from before 11/2026: the bronze Stage CHECK still lists Idea/Exploration,
    silver and gold hold those stages. Afterwards everything says Ideation."""
    path = tmp_path / "before_ideation.db"
    get_engine(path).dispose()
    conn = sqlite3.connect(path)
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (USER_ACTION_TABLE_NAME,)).fetchone()[0]
    old_sql = sql.replace("'Ideation'", "'Idea', 'Exploration'")
    assert old_sql != sql
    conn.executescript(f"""
        DROP TABLE "{USER_ACTION_TABLE_NAME}";
        {old_sql};
        INSERT INTO "{USER_ACTION_TABLE_NAME}" ("ID", "Timestamp", "SourceFileID", "SubmittedBy", "ActionType", "UseCaseID", "Stage")
            VALUES (1, '2026-10-30 10:00:00', 'ui', 'jonas', 'update', 1, 'Idea'),
                   (2, '2026-10-30 11:00:00', 'ui', 'jonas', 'update', 2, 'Exploration'),
                   (3, '2026-10-30 12:00:00', 'ui', 'jonas', 'update', 1, 'PoC');
        INSERT INTO "Owner" ("ID", "Name") VALUES (1, 'Owner A');
        INSERT INTO "ValueType" ("ID", "Name") VALUES (1, 'CAPEX delivery');
        INSERT INTO "BusinessTransaction" ("ID", "BronzeID", "BronzeTableName") VALUES (1, 1, 'UserActionExtracts');
    """)
    conn.commit()
    conn.close()
    engine = get_engine(path)
    with Session(engine) as s:
        for use_case_id, stage in ((1, "Idea"), (2, "Exploration")):
            s.add(Initiative(use_case_id=use_case_id, name=f"UC {use_case_id}", owner_id=1, value_type_id=1,
                             stage=stage, status="approved", key_hash=f"k{use_case_id}", row_hash=f"r{use_case_id}",
                             business_transaction_id=1, timestamp=datetime.datetime(2026, 10, 1)))
        s.commit()
    engine.dispose()

    for _ in range(2):  # idempotent
        engine = get_engine(path)
        with engine.connect() as c:
            rows = c.execute(select(USER_ACTION_TABLE.c.ID, USER_ACTION_TABLE.c.Stage).order_by(USER_ACTION_TABLE.c.ID)).all()
            definition = c.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name = ?", (USER_ACTION_TABLE_NAME,)).scalar()
        assert [tuple(r) for r in rows] == [(1, "Ideation"), (2, "Ideation"), (3, "PoC")]
        assert "'Idea'" not in definition and "'Ideation'" in definition
        with Session(engine) as s:
            assert {i.stage for i in s.scalars(select(Initiative))} == {"Ideation"}
        engine.dispose()
