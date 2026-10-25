"""The input form's mode of BronzeToSilver: formulas against the shared
fixture, and the incremental upsert against a temporary SQLite file
(pytest tests/)."""
import datetime
import json
from pathlib import Path

import pytest
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.models import (
    EXTRACT_TABLES,
    USER_INPUT_TABLE,
    USER_INPUT_TABLE_NAME,
    BusinessTransaction,
    Initiative,
    Owner,
    RiskClassification,
    SolutionType,
    ValueType,
)
from ai_cockpit_ingestion.operators.bronze_to_silver import BronzeToSilverOperator
from ai_cockpit_ingestion.sources import BRONZE_TO_SILVER_SOURCES, SOURCES, SOURCES_BY_KEY
from ai_cockpit_ingestion.transforms.risk_heuristic import RISK_LEVELS
from ai_cockpit_ingestion.transforms.user_input_heuristic import (
    estimate_user_input_value,
    quarter_start,
    user_input_risk_level,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "user_input_cases.json").read_text())


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=[c["name"] for c in FIXTURE["cases"]])
def test_formulas_match_the_shared_fixture(case):
    record = {**FIXTURE["base"], **case["input"]}
    expected = case["expected"]
    assert user_input_risk_level(record).level == expected["riskLevel"]
    if "efficiency" not in expected:
        return
    v = estimate_user_input_value(record)
    actual = {
        "efficiency": v.efficiency_eur, "quality": v.quality_eur, "riskReduction": v.risk_reduction_eur,
        "strategic": v.strategic_eur, "hypothetical": v.hypothetical_eur,
        "confidenceScore": v.confidence_score, "deliveryScore": v.delivery_score,
        "potential": v.hypothetical_eur * v.confidence_score * v.delivery_score,
        "oneTimeCosts": v.one_time_costs, "operatingCosts": v.operating_costs,
        "depreciationYears": v.depreciation_years,
        "annualCost": v.one_time_costs / v.depreciation_years + v.operating_costs,
    }
    for key, value in expected.items():
        if key != "riskLevel":
            assert actual[key] == pytest.approx(value), key


def test_quarter_start():
    assert quarter_start("Q2 2027") == datetime.datetime(2027, 4, 1)
    assert quarter_start(None) is None


def test_user_input_is_a_bronze_to_silver_source_but_not_a_sheet():
    assert SOURCES_BY_KEY["user_input"].extract_table == USER_INPUT_TABLE_NAME
    assert "user_input" not in {s.key for s in SOURCES}  # RawToBronze and seed_config stay sheet-only
    assert BRONZE_TO_SILVER_SOURCES[-1].key == "user_input"


# --- upsert ------------------------------------------------------------------


@pytest.fixture()
def engine(tmp_path):
    engine = get_engine(tmp_path / "test.db")
    with Session(engine) as s, s.begin():
        s.add_all([RiskClassification(**level) for level in RISK_LEVELS])
        s.add_all([SolutionType(id=1, name="Custom agent"), ValueType(id=1, name="CAPEX delivery")])
        s.add_all([
            Owner(id=1, category="ETB", name="Owner A", department="Assets"),
            Owner(id=2, category="IT", name="Owner B", department="Innovation"),
        ])
    yield engine
    engine.dispose()


def _submit(engine, name, owner_id=1, **over):
    record = {
        **FIXTURE["base"], **FIXTURE["cases"][0]["input"],
        "Timestamp": datetime.datetime(2026, 10, 25, 13, 0), "SubmittedBy": "jonas",
        "Name": name, "Description": f"About {name}", "OwnerID": owner_id, "ValueTypeID": 1, "SolutionTypeID": 1,
        "Stage": "Idea", "DateStart": None, "DateDelivery": "Q3 2027", "SolutionComplexityScore": 4,
        **over,
    }
    with engine.begin() as conn:
        return conn.execute(insert(USER_INPUT_TABLE).values(record)).inserted_primary_key[0]


def _silver(engine, source="user_input", force=False):
    op = BronzeToSilverOperator(task_id="t", source_key=source, db_path=str(engine.url.database))
    return op.execute({"params": {"force": force}})


def _initiatives(engine):
    with Session(engine) as s:
        return {i.name: i for i in s.scalars(select(Initiative))}


def test_new_records_become_initiatives_incrementally(engine):
    first = _submit(engine, "Smart Invoice Check")
    assert _silver(engine) == {"read": 1, "inserted": 1, "updated": 0, "conflicts": 0}
    i = _initiatives(engine)["Smart Invoice Check"]
    assert (i.owner_id, i.stage, i.date_delivery) == (1, "Idea", datetime.datetime(2027, 7, 1))
    assert (i.efficiency_score_eur, i.quality_score_eur) == (90000, 192000)
    assert (i.confidence_score, i.delivery_score, i.one_time_costs, i.depreciation_years) == (0.6, 0.65, 130000, 5)
    assert (i.solution_complexity_score, i.risk_classification_id, i.is_active) == (4.0, 2, True)
    with Session(engine) as s:
        bt = s.get(BusinessTransaction, i.business_transaction_id)
        assert (bt.bronze_table_name, bt.bronze_id) == (USER_INPUT_TABLE_NAME, first)

    # nothing new -> nothing read; a second submission only adds its own initiative
    assert _silver(engine)["read"] == 0
    _submit(engine, "Second", EmployeePersonalData="yes")
    assert _silver(engine) == {"read": 1, "inserted": 1, "updated": 0, "conflicts": 0}
    assert _initiatives(engine)["Second"].risk_classification_id == 3


def test_business_unit_comes_from_the_owner(engine):
    # same name in two business units -> two initiatives, KeyHash = business unit + name
    _submit(engine, "Twin", owner_id=1)
    _submit(engine, "Twin", owner_id=2)
    assert _silver(engine)["inserted"] == 2


def test_force_recomputes_all_records(engine):
    _submit(engine, "Alpha")
    _submit(engine, "Beta")
    _silver(engine)
    assert _silver(engine, force=True) == {"read": 2, "inserted": 0, "updated": 2, "conflicts": 0}


def test_key_of_a_sheet_initiative_is_a_conflict_and_leaves_it_untouched(engine):
    # a sheet initiative "Alpha" of business unit IT
    it = SOURCES_BY_KEY["it"]
    row = {c: None for c in it.columns} | {"Name": "Alpha", "Owner": "Owner B", "Department": "Innovation",
                                           "Status": "PoC", "Solution Type": "Custom agent"}
    with Session(engine) as s, s.begin():
        s.execute(insert(EXTRACT_TABLES[it.extract_table]),
                  [row | {"Timestamp": datetime.datetime(2026, 10, 23), "SourceFileID": "load.xlsx"}])
    _silver(engine, source="it")
    before = _initiatives(engine)["Alpha"]

    _submit(engine, " alpha ", owner_id=2)
    assert _silver(engine) == {"read": 1, "inserted": 0, "updated": 0, "conflicts": 1}
    after = _initiatives(engine)["Alpha"]
    assert (after.id, after.stage, after.business_transaction_id) == (before.id, "PoC", before.business_transaction_id)


def test_sheet_runs_do_not_deactivate_user_input(engine):
    _submit(engine, "Gamma", owner_id=2)
    _silver(engine)
    it = SOURCES_BY_KEY["it"]
    with Session(engine) as s, s.begin():
        s.execute(insert(EXTRACT_TABLES[it.extract_table]),
                  [{c: None for c in it.columns} | {"Name": "Other", "Status": "Idea",
                   "Timestamp": datetime.datetime(2026, 10, 23), "SourceFileID": "load.xlsx"}])
    _silver(engine, source="it")
    assert _initiatives(engine)["Gamma"].is_active is True
