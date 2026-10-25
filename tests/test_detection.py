"""New-data detection of the bronze_to_silver sensors: the table's newest record
against the start of the DAG's last successful transformation (pytest tests/)."""
import datetime

import pytest
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.detection import is_new
from ai_cockpit_ingestion.models import EXTRACT_TABLES, USER_INPUT_TABLE, Initiative, Owner, RiskClassification, SolutionType, ValueType
from ai_cockpit_ingestion.operators import new_bronze_sensor
from ai_cockpit_ingestion.operators.bronze_to_silver import BronzeToSilverOperator
from ai_cockpit_ingestion.operators.new_bronze_sensor import NewBronzeDataSensor
from ai_cockpit_ingestion.sources import BRONZE_TO_SILVER_SOURCES, SOURCES_BY_KEY
from ai_cockpit_ingestion.transforms.risk_heuristic import RISK_LEVELS

UTC = datetime.timezone.utc
IT = SOURCES_BY_KEY["it"]
T0 = datetime.datetime(2026, 10, 25, 12, 0)  # naive UTC, as bronze stores it


def test_is_new():
    assert is_new(None, None) is False  # empty table
    assert is_new(T0, None) is True  # never transformed
    assert is_new(T0, T0.replace(tzinfo=UTC) + datetime.timedelta(seconds=1)) is False
    assert is_new(T0, T0.replace(tzinfo=UTC) - datetime.timedelta(seconds=1)) is True


def test_is_new_compares_in_utc():
    # 13:30 Berlin (CET, UTC+1) is 12:30 UTC: a record from 12:00 UTC is older
    berlin = datetime.timezone(datetime.timedelta(hours=1))
    assert is_new(T0, datetime.datetime(2026, 10, 25, 13, 30, tzinfo=berlin)) is False
    assert is_new(T0, datetime.datetime(2026, 10, 25, 12, 30, tzinfo=berlin)) is True  # = 11:30 UTC


def test_a_record_written_while_the_transformation_ran_is_new():
    started = (T0 - datetime.timedelta(seconds=5)).replace(tzinfo=UTC)
    written_during_the_run = T0  # after the start, before the end
    assert is_new(written_during_the_run, started) is True


# --- sensor against a temporary database ---------------------------------------------


@pytest.fixture()
def engine(tmp_path):
    engine = get_engine(tmp_path / "test.db")
    with Session(engine) as s, s.begin():
        s.add_all([RiskClassification(**level) for level in RISK_LEVELS])
        s.add_all([SolutionType(id=1, name="Copilot"), ValueType(id=1, name="CAPEX delivery")])
        s.add(Owner(id=1, category="IT", name="Owner A", department="Innovation"))
    yield engine
    engine.dispose()


@pytest.fixture()
def last_start(monkeypatch):
    """The start of the last successful transformation, as the Airflow metadata DB would report it."""
    state = {"value": None}
    monkeypatch.setattr(new_bronze_sensor, "last_successful_start", lambda _dag_id: state["value"])
    return state


def _poke(engine, key, force=False):
    sensor = NewBronzeDataSensor(task_id=f"w_{key}", source_key=key, db_path=str(engine.url.database))
    return sensor.poke({"params": {"force": force}})


def _load_it(engine, at, names=("Alpha",)):
    with Session(engine) as s, s.begin():
        s.execute(insert(EXTRACT_TABLES[IT.extract_table]), [
            {c: None for c in IT.columns} | {"Name": n, "Status": "Idea", "Timestamp": at, "SourceFileID": "x.xlsx"}
            for n in names
        ])


def _submit(engine, at):
    with engine.begin() as conn:
        conn.execute(insert(USER_INPUT_TABLE).values(
            Timestamp=at, SubmittedBy="t", Name="New", Description="d",
            OwnerID=1, ValueTypeID=1, SolutionTypeID=1, Stage="Idea", CasesPerYear=10, HoursSavedPerCase=1,
            EstimateBasis="rough", DeliveryLikelihood="low", SolutionComplexityScore=3, OneTimeCosts=0,
            OperatingCosts=0, EmployeePersonalData="no", PerformanceOrBehaviourControl=False,
            DecisionsOnEmployees="none", ProfilingOfIndividuals=False, ChangesEmployeeWorkflows=False,
            ProhibitedPractice=False,
        ))


def test_sensor_waits_on_an_empty_table(engine, last_start):
    assert [_poke(engine, s.key) for s in BRONZE_TO_SILVER_SOURCES] == [False] * 5


def test_sheet_sensor_fires_for_a_load_after_the_last_transformation(engine, last_start):
    _load_it(engine, T0)
    assert _poke(engine, "it") is True  # never transformed
    last_start["value"] = (T0 + datetime.timedelta(minutes=1)).replace(tzinfo=UTC)
    assert _poke(engine, "it") is False
    _load_it(engine, T0 + datetime.timedelta(minutes=2))
    assert _poke(engine, "it") is True
    assert _poke(engine, "50hertz") is False  # only its own table


def test_user_input_sensor_fires_for_a_new_submission(engine, last_start):
    _submit(engine, T0)
    assert _poke(engine, "user_input") is True
    last_start["value"] = (T0 + datetime.timedelta(seconds=30)).replace(tzinfo=UTC)
    assert _poke(engine, "user_input") is False
    _submit(engine, T0 + datetime.timedelta(minutes=1))
    assert _poke(engine, "user_input") is True


def test_force_fires_whenever_the_table_has_data(engine, last_start):
    last_start["value"] = (T0 + datetime.timedelta(days=1)).replace(tzinfo=UTC)
    _load_it(engine, T0)
    assert _poke(engine, "it", force=True) is True
    assert _poke(engine, "etb", force=True) is False  # nothing to transform


def test_a_repeated_transformation_changes_nothing(engine, last_start):
    # the sensor may fire again for a load already transformed (e.g. clock skew): the hash
    # check keeps silver as it is
    _load_it(engine, T0, names=("Alpha", "Beta"))
    op = BronzeToSilverOperator(task_id="t", source_key="it", db_path=str(engine.url.database))
    op.execute({"params": {}})
    with Session(engine) as s:
        before = {(i.id, i.business_transaction_id, i.timestamp) for i in s.scalars(select(Initiative))}
    assert op.execute({"params": {}})["unchanged"] == 2
    with Session(engine) as s:
        assert {(i.id, i.business_transaction_id, i.timestamp) for i in s.scalars(select(Initiative))} == before
