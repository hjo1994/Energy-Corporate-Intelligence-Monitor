"""Hashing and the silver upsert against a temporary SQLite file (no Airflow
scheduler and no source workbook needed): pytest tests/
"""
import datetime

import pytest
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.models import (
    EXTRACT_TABLES,
    current_versions,
    BusinessTransaction,
    Initiative,
    Owner,
    RiskClassification,
    SolutionType,
    ValueType,
)
from ai_cockpit_ingestion.operators.bronze_to_silver import BronzeToSilverOperator
from ai_cockpit_ingestion.sources import SOURCES_BY_KEY
from ai_cockpit_ingestion.operators.user_input_to_silver import RISK_ANSWER_ATTRIBUTES
from ai_cockpit_ingestion.transforms.risk_heuristic import RISK_LEVELS, estimate_risk_level, risk_answers_for_level
from ai_cockpit_ingestion.transforms.user_input_heuristic import user_input_risk_level
from ai_cockpit_ingestion.transforms.upsert_keys import key_hash, row_hash, row_hash_columns

IT = SOURCES_BY_KEY["it"]


# --- hashes ------------------------------------------------------------------


def test_key_hash_normalizes_whitespace_case_and_invisible_chars():
    base = key_hash("ETB", "AC_012 check reporting")
    assert key_hash("ETB", " ac_012\xa0 CHECK reporting​ ") == base
    assert key_hash("IT", "AC_012 check reporting") != base  # business unit is part of the key
    assert key_hash("ETB", "AC_013 check reporting") != base  # a rename is a new key


def test_row_hash_covers_only_the_silver_relevant_columns_of_the_sheet():
    columns = row_hash_columns(IT.columns)
    assert "Name" in columns and "Added Value" in columns
    assert not {"Number", "Strategic Link", "Impediments", "Value", "Timing start"} & set(columns)
    row = {c: f"v {c}" for c in IT.columns}
    base = row_hash(row, columns)
    assert row_hash(row | {"Number": "99", "Impediments": "new", "Strategic Link": "x"}, columns) == base
    assert row_hash(row | {"Description": "  v   Description "}, columns) == base  # whitespace only
    assert row_hash(row | {"Description": "changed"}, columns) != base
    assert row_hash(row | {"Description": None}, columns) == row_hash(row | {"Description": ""}, columns)


# --- upsert ------------------------------------------------------------------


@pytest.fixture()
def engine(tmp_path):
    engine = get_engine(tmp_path / "test.db")
    with Session(engine) as s, s.begin():
        s.add_all([RiskClassification(**level) for level in RISK_LEVELS])
        s.add_all([SolutionType(name="Copilot"), ValueType(name="CAPEX delivery")])
        s.add(Owner(category="IT", name="Owner A", department="Innovation"))
    yield engine
    engine.dispose()


def _row(name, **over):
    row = {c: None for c in IT.columns}
    row.update({"Name": name, "Description": f"About {name}", "Owner": "Owner A", "Department": "Innovation",
                "Status": "Idea", "Solution Type": "Copilot", "Flagship": "CAPEX delivery"})
    row.update(over)
    return row


_loads = 0


def _load(engine, rows):
    """Append one bronze load like RawToBronze does (one Timestamp per load)."""
    global _loads
    _loads += 1
    stamp = datetime.datetime(2026, 10, 23) + datetime.timedelta(minutes=_loads)
    with Session(engine) as s, s.begin():
        s.execute(insert(EXTRACT_TABLES[IT.extract_table]),
                  [{**r, "Timestamp": stamp, "SourceFileID": f"load{_loads}.xlsx"} for r in rows])


def _silver(engine, force=False):
    """Runs the IT DAG; returns its counts and the current version per name
    as (UseCaseID, IsActive, BusinessTransactionID)."""
    op = BronzeToSilverOperator(task_id="t", source_key="it", db_path=str(engine.url.database))
    counts = op.execute({"params": {"force": force}})
    with Session(engine) as s:
        rows = {i.name: (i.use_case_id, i.is_active, i.business_transaction_id) for i in s.scalars(current_versions())}
        return counts, rows


def _versions(engine, name):
    with Session(engine) as s:
        return s.scalars(select(Initiative).where(Initiative.name == name).order_by(Initiative.id)).all()


def _counts(**over):
    return {"inserted": 0, "updated": 0, "unchanged": 0, "deactivated": 0, "conflicts": 0, "ui_owned": 0, **over}


def test_insert_unchanged_new_version_deactivate_and_force(engine):
    _load(engine, [_row("Alpha"), _row("Beta"), _row("Gamma")])
    counts, first = _silver(engine)
    assert counts == _counts(inserted=3)
    assert sorted(uc for uc, _, _ in first.values()) == [1, 2, 3]  # one new use case each

    # same content again (bronze grows, silver untouched)
    _load(engine, [_row("Alpha"), _row("Beta"), _row("Gamma")])
    counts, second = _silver(engine)
    assert counts == _counts(unchanged=3)
    assert second == first  # still the first versions, pointing to the first transaction
    with Session(engine) as s:
        assert len(s.execute(select(EXTRACT_TABLES[IT.extract_table])).all()) == 6
        # one BusinessTransaction per version, pointing to its bronze record
        bts = s.scalars(select(BusinessTransaction)).all()
        assert len(bts) == 3 and {b.bronze_table_name for b in bts} == {IT.extract_table}
        assert sorted(b.bronze_id for b in bts) == [1, 2, 3]

    # change Alpha, drop Beta, add Delta; Number/Impediments changes alone are no delta
    _load(engine, [_row("Alpha", Status="PoC"), _row("Gamma", Number="7", Impediments="x"), _row("Delta")])
    counts, third = _silver(engine)
    assert counts == _counts(inserted=1, updated=1, unchanged=1, deactivated=1)
    alpha = _versions(engine, "Alpha")
    assert [(v.use_case_id, v.stage) for v in alpha] == [(1, "Ideation"), (1, "PoC")]  # appended, first kept
    assert third["Alpha"][2] != first["Alpha"][2]  # the new version has a new BusinessTransaction
    assert third["Beta"] == (first["Beta"][0], False, first["Beta"][2])  # soft delete = copy, keeps its BT
    assert [v.is_active for v in _versions(engine, "Beta")] == [True, False]
    assert third["Gamma"] == first["Gamma"]
    assert third["Delta"][:2] == (4, True)

    # Beta comes back -> a new active version of the same use case
    _load(engine, [_row("Alpha", Status="PoC"), _row("Beta"), _row("Gamma"), _row("Delta")])
    counts, fourth = _silver(engine)
    assert counts == _counts(updated=1, unchanged=3) and fourth["Beta"][:2] == (first["Beta"][0], True)

    # force recomputes everything, but only a changed result is a new version
    with Session(engine) as s:
        before = s.query(Initiative).count()
    counts, _ = _silver(engine, force=True)
    assert counts == _counts(unchanged=4)
    with Session(engine) as s:
        assert s.query(Initiative).count() == before


def test_sheet_rows_get_the_canonical_risk_answers_of_their_estimated_level(engine):
    _load(engine, [_row("Alpha"), _row("HR", Description="Recruiting: applicant screening")])
    _silver(engine)
    alpha, hr = _versions(engine, "Alpha")[0], _versions(engine, "HR")[0]
    assert user_input_risk_level(_answers(alpha)).level == estimate_risk_level(
        name="Alpha", description="About Alpha", solution_type="Copilot").level
    assert (hr.decisions_on_employees, user_input_risk_level(_answers(hr)).level) == ("automated", 4)
    assert (alpha.status, alpha.running_costs is not None) == (None, True)


def _answers(version):
    return {c: getattr(version, a) for c, a in RISK_ANSWER_ATTRIBUTES.items()}


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
def test_risk_answers_for_level_yield_that_level(level):
    assert user_input_risk_level(risk_answers_for_level(level)).level == level


def test_duplicate_keys_in_one_load(engine):
    _load(engine, [_row("Alpha"), _row("Alpha "), _row("Beta", Status="Idea"), _row("Beta", Status="PoC")])
    counts, rows = _silver(engine)
    # identical content -> taken once; different content -> conflict, not taken
    assert counts == _counts(inserted=1, conflicts=1)
    assert list(rows) == ["Alpha"]


def test_conflict_keeps_existing_row(engine):
    _load(engine, [_row("Beta")])
    _silver(engine)
    _load(engine, [_row("Beta", Status="Idea"), _row("Beta", Status="PoC")])
    counts, rows = _silver(engine)
    assert counts["conflicts"] == 1 and counts["deactivated"] == 0
    assert rows["Beta"][1] is True
