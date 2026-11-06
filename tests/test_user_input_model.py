"""The user-input bronze table: created with the data model, typed and
guarded by constraints (pytest tests/)."""
import datetime

import pytest
from sqlalchemy import inspect, insert
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.models import USER_ACTION_TABLE, USER_ACTION_TABLE_NAME, Owner, SolutionType, ValueType


@pytest.fixture()
def engine(tmp_path):
    engine = get_engine(tmp_path / "test.db")
    with Session(engine) as s, s.begin():
        s.add_all([
            Owner(id=1, category="ETB", name="Owner A", department="Assets"),
            ValueType(id=1, name="CAPEX delivery"),
            SolutionType(id=1, name="Custom agent"),
        ])
    yield engine
    engine.dispose()


def record(**over):
    return {
        "Timestamp": datetime.datetime(2026, 10, 25, 13, 0),
        "SubmittedBy": "jonas",
        "ActionType": "create",
        "Name": "Smart Invoice Check",
        "Description": "Checks incoming invoices against the order",
        "OwnerID": 1,
        "ValueTypeID": 1,
        "SolutionTypeID": 1,
        "Stage": "Ideation",
        "DateStart": "Q1 2027",
        "DateDelivery": None,
        "CasesPerYear": 3000,
        "HoursSavedPerCase": 0.5,
        "ErrorRateBefore": 0.08,
        "ErrorsAvoided": 0.4,
        "CostPerError": 2000,
        "EstimateBasis": "benchmark",
        "DeliveryLikelihood": "medium",
        "SolutionComplexityScore": 4,
        "OneTimeCosts": 200_000,
        "OperatingCosts": 50_000,
        "EmployeePersonalData": "no",
        "PerformanceOrBehaviourControl": False,
        "DecisionsOnEmployees": "none",
        "ProfilingOfIndividuals": False,
        "ChangesEmployeeWorkflows": True,
        "ProhibitedPractice": False,
        **over,
    }


def add(engine, **over):
    with engine.begin() as conn:
        return conn.execute(insert(USER_ACTION_TABLE).values(record(**over))).inserted_primary_key[0]


def test_table_is_created_with_the_data_model(engine):
    inspector = inspect(engine)
    assert USER_ACTION_TABLE_NAME in inspector.get_table_names()
    columns = [c["name"] for c in inspector.get_columns(USER_ACTION_TABLE_NAME)]
    assert columns[:4] == ["ID", "Timestamp", "SourceFileID", "SubmittedBy"]
    assert {"ActionType", "UseCaseID", "NeedsGateDate", "RetireGateDate", "LeadID", "CasesPerYear", "LeadTimeSaved", "EstimateBasis",
            "ProhibitedPractice", "AILayer", "MeasuredBenefits", "ActualCapex", "ActualOpex"} <= set(columns)
    assert len(columns) == 63
    assert {fk["referred_table"] for fk in inspector.get_foreign_keys(USER_ACTION_TABLE_NAME)} == {
        "AppUser", "Owner", "ValueType", "SolutionType",
    }
    assert sorted(i["column_names"] for i in inspector.get_indexes(USER_ACTION_TABLE_NAME)) == [
        ["Timestamp"], ["UseCaseID"],
    ]


def test_valid_record_is_stored_with_empty_levers_left_null(engine):
    assert add(engine) == 1
    with engine.connect() as conn:
        row = conn.execute(USER_ACTION_TABLE.select()).one()._mapping
    assert row["SourceFileID"] == "user-input"
    assert row["RiskEventsPerYear"] is None and row["LeadTimeSaved"] is None


@pytest.mark.parametrize(
    "over",
    [
        {"Stage": "Pilot"},
        {"DateStart": "2027-01-01"},
        {"DateDelivery": "Q5 2027"},
        {"CasesPerYear": -1},
        {"ErrorRateBefore": 8},  # a percentage, not a share
        {"EventsAvoided": 1.5},
        {"EstimateBasis": "guess"},
        {"DeliveryLikelihood": "certain"},
        {"SolutionComplexityScore": 10},
        {"SolutionComplexityScore": 0},
        {"OneTimeCosts": -5},
        {"EmployeePersonalData": "maybe"},
        {"DecisionsOnEmployees": "decides"},
        {"ProhibitedPractice": 2},
        {"Name": None},
        {"OneTimeCosts": None},
        {"OwnerID": 99},  # not in the config
        {"ValueTypeID": 99},
        {"ActionType": "delete"},
        {"Status": "done"},
        {"AILayer": "Some AI"},
        {"EUAIActClass": "medium"},
        {"Stage": "Archived"},
        {"ActionType": "update"},  # without UseCaseID
        {"ActionType": "approve", "UseCaseID": 1},  # without LeadID
        {"ActionType": "reject", "UseCaseID": 1},  # without Comment
        {"ExpectedUsers": -1},
        {"ActualOpex": -1},
    ],
)
def test_constraints_reject_invalid_input(engine, over):
    # IntegrityError from the database, or StatementError where SQLAlchemy refuses first (Boolean)
    with pytest.raises(StatementError):
        add(engine, **over)


def test_update_needs_only_the_use_case_and_what_changes(engine):
    add(engine)
    update = {c: None for c in record()} | {
        "Timestamp": datetime.datetime(2026, 11, 1), "SubmittedBy": "sara", "ActionType": "update", "UseCaseID": 1,
        "AILayer": "Operational and advanced AI", "Stage": "Retired", "RetireGateDate": datetime.datetime(2026, 11, 1),
    }
    with engine.begin() as conn:
        conn.execute(insert(USER_ACTION_TABLE).values(update))
        conn.execute(insert(USER_ACTION_TABLE).values(
            {k: None for k in update} | {"Timestamp": update["Timestamp"], "SubmittedBy": "lena", "ActionType": "approve",
                                         "UseCaseID": 1, "LeadID": 1}))
