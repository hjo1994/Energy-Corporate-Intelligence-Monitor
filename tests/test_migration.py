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
        assert "Email" in {c["name"] for c in inspector.get_columns("Owner")}
        assert {"AssessedInitiatives", USER_ACTION_TABLE_NAME, "UserInput_Initiatives_Extract"} <= set(
            inspector.get_table_names())
        with engine.connect() as conn:
            action = conn.execute(select(USER_ACTION_TABLE)).one()._mapping
            assert (action["ID"], action["ActionType"], action["UseCaseID"], action["Name"]) == (
                1, "create", None, "Smart Invoice Check")
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
