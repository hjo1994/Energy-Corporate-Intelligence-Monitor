"""SilverToGold: formulas, the due detection and the gold upsert, against a
temporary SQLite file (pytest tests/)."""
import datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.models import (
    USER_ACTION_TABLE,
    AssessedInitiative,
    Owner,
    RiskClassification,
    SolutionType,
    TransformationRun,
    ValueType,
)
from ai_cockpit_ingestion.operators.bronze_to_silver import BronzeToSilverOperator
from ai_cockpit_ingestion.operators.silver_to_gold import (
    SilverChangesSensor,
    SilverToGoldOperator,
    assess_into_gold,
    due_use_cases,
)
from ai_cockpit_ingestion.transforms.gold import MANDATORY, assess, is_complete, missing_mandatory
from ai_cockpit_ingestion.transforms.risk_heuristic import RISK_LEVELS, risk_answers_for_level

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "user_input_cases.json").read_text())
TODAY = datetime.date(2026, 11, 1)


def _version(**over):
    base = {a: 0.0 for a in MANDATORY} | {
        "efficiency_score_eur": 90_000.0, "quality_score_eur": 192_000.0, "risk_reduction_score_eur": 50_000.0,
        "strategic_value_score_eur": 150_000.0, "confidence_score": 0.6, "delivery_score": 0.65,
        "one_time_costs": 130_000.0, "running_costs": 32_500.0, "date_delivery": None,
        "measured_benefits": None, "actual_costs": None,
    }
    answers = {"employee_personal_data": "no", "performance_or_behaviour_control": False,
               "decisions_on_employees": "none", "profiling_of_individuals": False,
               "changes_employee_workflows": True, "prohibited_practice": False}
    return SimpleNamespace(**(base | answers | over))


# --- formulas ----------------------------------------------------------------


def test_potential_value_matches_the_shared_fixture():
    expected = FIXTURE["cases"][0]["expected"]
    result = assess(_version(), TODAY)
    assert result.potential_value == pytest.approx(expected["potential"])
    assert (result.realized_value, result.risk_level, result.runtime_based) == (None, expected["riskLevel"], False)


def test_realized_value_from_runtime_after_delivery():
    two_years_ago = datetime.datetime(2024, 11, 1)
    result = assess(_version(date_delivery=two_years_ago), TODAY)
    runtime = (TODAY - two_years_ago.date()).days / 365.25
    assert result.realized_value == pytest.approx(187_980 * runtime - (130_000 + 32_500 * runtime))
    assert result.runtime_based is True
    # not delivered yet -> no realized value
    assert assess(_version(date_delivery=datetime.datetime(2027, 1, 1)), TODAY).realized_value is None


def test_realized_value_from_real_values_wins():
    result = assess(_version(date_delivery=datetime.datetime(2024, 1, 1), measured_benefits=80_000,
                             actual_costs=23_000), TODAY)
    assert (result.realized_value, result.runtime_based) == (57_000, False)


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
def test_risk_level_from_the_answers(level):
    answers = {
        "employee_personal_data": risk_answers_for_level(level)["EmployeePersonalData"],
        "performance_or_behaviour_control": False,
        "decisions_on_employees": risk_answers_for_level(level)["DecisionsOnEmployees"],
        "profiling_of_individuals": False,
        "changes_employee_workflows": risk_answers_for_level(level)["ChangesEmployeeWorkflows"],
        "prohibited_practice": risk_answers_for_level(level)["ProhibitedPractice"],
    }
    assert assess(_version(**answers), TODAY).risk_level == level


@pytest.mark.parametrize("attribute", MANDATORY)
def test_every_mandatory_attribute_is_needed(attribute):
    version = _version(**{attribute: None})
    assert not is_complete(version) and missing_mandatory(version) == [attribute]


# --- DAG ---------------------------------------------------------------------


@pytest.fixture()
def engine(tmp_path):
    engine = get_engine(tmp_path / "test.db")
    with Session(engine) as s, s.begin():
        s.add_all([RiskClassification(**level) for level in RISK_LEVELS])
        s.add_all([SolutionType(id=1, name="Custom agent"), ValueType(id=1, name="CAPEX delivery")])
        s.add(Owner(id=1, category="ETB", name="Owner A", department="Assets"))
    yield engine
    engine.dispose()


def _action(engine, **values):
    record = {"Timestamp": datetime.datetime(2026, 10, 25, 13, 0), "SubmittedBy": "jonas", **values}
    with engine.begin() as conn:
        conn.execute(insert(USER_ACTION_TABLE).values(record))
    BronzeToSilverOperator(task_id="t", source_key="user_input", db_path=str(engine.url.database)).execute({})


def _create(engine, name, **over):
    _action(engine, **{
        **FIXTURE["base"], **FIXTURE["cases"][0]["input"], "ActionType": "create", "Name": name,
        "Description": f"About {name}", "OwnerID": 1, "ValueTypeID": 1, "Stage": "Idea",
        "DateDelivery": "Q3 2027", "SolutionComplexityScore": 4, **over,
    })


def _gold(engine, force=False):
    return SilverToGoldOperator(task_id="g", db_path=str(engine.url.database)).execute({"params": {"force": force}})


def _rows(engine):
    with Session(engine) as s:
        return {g.name: g for g in s.scalars(select(AssessedInitiative))}


def _poke(engine, force=False):
    return SilverChangesSensor(task_id="w", db_path=str(engine.url.database)).poke({"params": {"force": force}})


def test_new_use_case_is_assessed_once_and_reassessed_when_it_changes(engine):
    assert _poke(engine) is False
    _create(engine, "Alpha")
    assert _poke(engine) is True
    assert _gold(engine) == {"read": 1, "inserted": 1, "updated": 0, "unchanged": 0}
    alpha = _rows(engine)["Alpha"]
    assert alpha.potential_value == pytest.approx(187_980)
    assert (alpha.use_case_id, alpha.status, alpha.risk_classification_id, alpha.realized_value) == (
        1, "pending", 2, None)
    assert _poke(engine) is False  # nothing due any more

    # a calculation attribute changes -> new silver version -> reassessed
    _action(engine, ActionType="update", UseCaseID=1, HoursSavedPerCase=1.0, EmployeePersonalData="yes")
    assert _poke(engine) is True
    assert _gold(engine)["updated"] == 1
    alpha = _rows(engine)["Alpha"]
    assert alpha.potential_value == pytest.approx((180_000 + 192_000 + 50_000 + 150_000) * 0.6 * 0.65)
    assert alpha.risk_classification_id == 3

    # a descriptive change (approval) is copied too, the values stay
    _action(engine, ActionType="approve", UseCaseID=1, LeadID=1)
    assert _gold(engine)["updated"] == 1
    assert (_rows(engine)["Alpha"].status, _rows(engine)["Alpha"].lead_id, _rows(engine)["Alpha"].stagegate) == (
        "approved", 1, "Needs")
    with Session(engine) as s:
        run = s.scalars(select(TransformationRun).order_by(TransformationRun.id.desc())).first()
        assert (run.bronze_table_name, run.status, run.rows_read, run.rows_updated) == ("Initiative", "success", 1, 1)


def test_runtime_based_realized_value_is_recomputed_daily(engine):
    _create(engine, "Delivered", DateDelivery="Q1 2025")
    with Session(engine) as s, s.begin():
        assess_into_gold(s, force=False, today=TODAY)
    with Session(engine) as s:
        first = s.scalars(select(AssessedInitiative)).one().realized_value
        assessed_at = s.scalars(select(AssessedInitiative)).one().assessed_at
        assert first is not None
        # due again only on a later day
        assert due_use_cases(s, assessed_at.date()) == []
        assert len(due_use_cases(s, assessed_at.date() + datetime.timedelta(days=1))) == 1


def test_force_reassesses_everything_without_changes(engine):
    _create(engine, "Alpha")
    _create(engine, "Beta")
    _gold(engine)
    assert _poke(engine, force=True) is True
    assert _gold(engine, force=True) == {"read": 2, "inserted": 0, "updated": 0, "unchanged": 2}
