"""New-data detection of the bronze_to_silver sensors and the TransformationRun
log behind it (pytest tests/)."""
import datetime

import pytest
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.detection import is_new
from ai_cockpit_ingestion.models import (
    EXTRACT_TABLES,
    USER_ACTION_TABLE,
    Initiative,
    Owner,
    RiskClassification,
    SolutionType,
    TransformationRun,
    ValueType,
)
from ai_cockpit_ingestion.operators.bronze_to_silver import BronzeToSilverOperator
from ai_cockpit_ingestion.operators.new_bronze_sensor import NewBronzeDataSensor
from ai_cockpit_ingestion.sources import BRONZE_TO_SILVER_SOURCES, SOURCES_BY_KEY
from ai_cockpit_ingestion.transforms.risk_heuristic import RISK_LEVELS

IT = SOURCES_BY_KEY["it"]
T0 = datetime.datetime(2026, 10, 25, 12, 0)  # naive UTC, as bronze stores it


def test_is_new():
    assert is_new(None, None) is False  # empty table
    assert is_new(T0, None) is True  # never transformed
    assert is_new(T0, T0) is False  # exactly what the last run had seen
    assert is_new(T0 + datetime.timedelta(microseconds=1), T0) is True


def test_is_new_compares_in_utc():
    # 13:30 Berlin (CET, UTC+1) is 12:30 UTC: a record from 12:00 UTC is older
    berlin = datetime.timezone(datetime.timedelta(hours=1))
    assert is_new(T0, datetime.datetime(2026, 10, 25, 13, 30, tzinfo=berlin)) is False
    assert is_new(T0, datetime.datetime(2026, 10, 25, 12, 30, tzinfo=berlin)) is True  # = 11:30 UTC


@pytest.fixture()
def engine(tmp_path):
    engine = get_engine(tmp_path / "test.db")
    with Session(engine) as s, s.begin():
        s.add_all([RiskClassification(**level) for level in RISK_LEVELS])
        s.add_all([SolutionType(id=1, name="Copilot"), ValueType(id=1, name="CAPEX delivery")])
        s.add(Owner(id=1, category="IT", name="Owner A", department="Innovation"))
    yield engine
    engine.dispose()


class _DagRun:
    run_id = "scheduled__2026-10-25T12:00:00+00:00"


def _poke(engine, key, force=False):
    sensor = NewBronzeDataSensor(task_id=f"w_{key}", source_key=key, db_path=str(engine.url.database))
    return sensor.poke({"params": {"force": force}})


def _transform(engine, key, force=False):
    op = BronzeToSilverOperator(task_id="t", source_key=key, db_path=str(engine.url.database))
    return op.execute({"params": {"force": force}, "dag_run": _DagRun()})


def _runs(engine):
    with Session(engine) as s:
        return s.scalars(select(TransformationRun).order_by(TransformationRun.id)).all()


def _load_it(engine, at, names=("Alpha",)):
    with Session(engine) as s, s.begin():
        s.execute(insert(EXTRACT_TABLES[IT.extract_table]), [
            {c: None for c in IT.columns} | {"Name": n, "Status": "Idea", "Timestamp": at, "SourceFileID": "x.xlsx"}
            for n in names
        ])


def _submit(engine, at, name="New"):
    with engine.begin() as conn:
        conn.execute(insert(USER_ACTION_TABLE).values(
            Timestamp=at, SubmittedBy="t", ActionType="create", Name=name, Description="d",
            OwnerID=1, ValueTypeID=1, SolutionTypeID=1, Stage="Ideation", CasesPerYear=10, HoursSavedPerCase=1,
            EstimateBasis="rough", DeliveryLikelihood="low", SolutionComplexityScore=3, OneTimeCosts=0,
            OperatingCosts=0, EmployeePersonalData="no", PerformanceOrBehaviourControl=False,
            DecisionsOnEmployees="none", ProfilingOfIndividuals=False, ChangesEmployeeWorkflows=False,
            ProhibitedPractice=False,
        ))


def test_sensors_wait_on_empty_tables(engine):
    assert [_poke(engine, s.key) for s in BRONZE_TO_SILVER_SOURCES] == [False] * 5


def test_sheet_load_is_new_until_a_successful_run_has_seen_it(engine):
    _load_it(engine, T0, names=("Alpha", "Beta"))
    assert _poke(engine, "it") is True  # no run yet
    _transform(engine, "it")
    assert _poke(engine, "it") is False
    assert _poke(engine, "50hertz") is False  # only its own table

    run = _runs(engine)[-1]
    assert (run.bronze_table_name, run.status, run.bronze_timestamp, run.dag_run_id) == (
        IT.extract_table, "success", T0, _DagRun.run_id)
    assert (run.rows_read, run.rows_inserted, run.rows_updated, run.rows_unchanged,
            run.rows_deactivated, run.rows_conflict) == (2, 2, 0, 0, 0, 0)
    assert run.started_at <= run.finished_at

    _load_it(engine, T0 + datetime.timedelta(minutes=5), names=("Alpha", "Beta"))
    assert _poke(engine, "it") is True  # next load, even with the same content
    _transform(engine, "it")
    assert (_runs(engine)[-1].rows_unchanged, _runs(engine)[-1].rows_inserted) == (2, 0)  # hash check


def test_first_run_on_existing_data_changes_nothing_in_silver(engine):
    # what happens after deployment: data already transformed, but no TransformationRun yet
    _load_it(engine, T0, names=("Alpha", "Beta"))
    _transform(engine, "it")
    with Session(engine) as s:
        s.query(TransformationRun).delete()
        s.commit()
        before = {(i.id, i.business_transaction_id, i.timestamp, i.row_hash) for i in s.scalars(select(Initiative))}
    assert _poke(engine, "it") is True
    counts = _transform(engine, "it")
    assert counts == {"inserted": 0, "updated": 0, "unchanged": 2, "deactivated": 0, "conflicts": 0, "ui_owned": 0}
    with Session(engine) as s:
        assert {(i.id, i.business_transaction_id, i.timestamp, i.row_hash) for i in s.scalars(select(Initiative))} == before
    assert _poke(engine, "it") is False


def test_a_record_written_during_a_run_is_new_for_the_next_one(engine, monkeypatch):
    _load_it(engine, T0)
    original = BronzeToSilverOperator._transform_sheet

    def while_a_new_load_arrives(self, session, *args, **kwargs):
        # stands for a writer that commits right after the run took max(Timestamp)
        with Session(engine) as other, other.begin():
            other.execute(insert(EXTRACT_TABLES[IT.extract_table]), [
                {c: None for c in IT.columns} | {"Name": "Late", "Status": "Idea",
                 "Timestamp": T0 + datetime.timedelta(minutes=1), "SourceFileID": "y.xlsx"}])
        return original(self, session, *args, **kwargs)

    monkeypatch.setattr(BronzeToSilverOperator, "_transform_sheet", while_a_new_load_arrives)
    _transform(engine, "it")
    assert _runs(engine)[-1].bronze_timestamp == T0  # taken before the data was read
    assert _poke(engine, "it") is True


def test_a_failed_run_is_logged_and_the_data_stays_new(engine, monkeypatch):
    _load_it(engine, T0)

    def boom(*_args, **_kw):
        raise RuntimeError("transform failed")

    monkeypatch.setattr(BronzeToSilverOperator, "_upsert", boom)
    with pytest.raises(RuntimeError):
        _transform(engine, "it")
    run = _runs(engine)[-1]
    assert (run.status, run.rows_read, run.finished_at is not None) == ("failed", None, True)
    assert _poke(engine, "it") is True


def test_user_input_submission_is_new_until_transformed(engine):
    _submit(engine, T0)
    assert _poke(engine, "user_input") is True
    _transform(engine, "user_input")
    run = _runs(engine)[-1]
    assert (run.status, run.rows_read, run.rows_inserted, run.rows_unchanged) == ("success", 1, 1, 0)
    assert _poke(engine, "user_input") is False
    _submit(engine, T0 + datetime.timedelta(minutes=1), name="Another")
    assert _poke(engine, "user_input") is True


def test_force_fires_whenever_the_table_has_data(engine):
    _load_it(engine, T0)
    _transform(engine, "it")
    assert _poke(engine, "it") is False
    assert _poke(engine, "it", force=True) is True
    assert _poke(engine, "etb", force=True) is False  # nothing to transform
