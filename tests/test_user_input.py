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
    AppUser,
    USER_ACTION_TABLE,
    USER_ACTION_TABLE_NAME,
    BusinessTransaction,
    Initiative,
    current_versions,
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
    assert SOURCES_BY_KEY["user_input"].extract_table == USER_ACTION_TABLE_NAME
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
        "Timestamp": datetime.datetime(2026, 10, 25, 13, 0), "SubmittedBy": "jonas", "ActionType": "create",
        "Name": name, "Description": f"About {name}", "OwnerID": owner_id, "ValueTypeID": 1, "SolutionTypeID": 1,
        "Stage": "Ideation", "DateStart": None, "DateDelivery": "Q3 2027", "SolutionComplexityScore": 4,
        **over,
    }
    with engine.begin() as conn:
        return conn.execute(insert(USER_ACTION_TABLE).values(record)).inserted_primary_key[0]


def _act(engine, action, use_case_id, **values):
    """Append a user action (update / approve / reject) with only the given fields."""
    record = {"Timestamp": datetime.datetime(2026, 11, 1, 9, 0), "SubmittedBy": "sara", "ActionType": action,
              "UseCaseID": use_case_id, **values}
    with engine.begin() as conn:
        return conn.execute(insert(USER_ACTION_TABLE).values(record)).inserted_primary_key[0]


def _silver(engine, source="user_input", force=False):
    op = BronzeToSilverOperator(task_id="t", source_key=source, db_path=str(engine.url.database))
    return op.execute({"params": {"force": force}})


def _counts(**over):
    return {"read": 0, "inserted": 0, "updated": 0, "unchanged": 0, "conflicts": 0, **over}


def _initiatives(engine):
    """Current version per name."""
    with Session(engine) as s:
        return {i.name: i for i in s.scalars(current_versions())}


def _versions(engine, use_case_id):
    with Session(engine) as s:
        return s.scalars(select(Initiative).where(Initiative.use_case_id == use_case_id).order_by(Initiative.id)).all()


def test_create_becomes_a_pending_use_case_incrementally(engine):
    first = _submit(engine, "Smart Invoice Check")
    assert _silver(engine) == _counts(read=1, inserted=1)
    i = _initiatives(engine)["Smart Invoice Check"]
    assert (i.use_case_id, i.status, i.changed_by) == (1, "pending", "jonas")
    assert (i.owner_id, i.stage, i.date_delivery) == (1, "Ideation", datetime.datetime(2027, 7, 1))
    assert (i.efficiency_score_eur, i.quality_score_eur) == (90000, 192000)
    assert (i.confidence_score, i.delivery_score, i.one_time_costs, i.running_costs, i.depreciation_years) == (
        0.6, 0.65, 130000, 32500, 5)
    assert (i.solution_complexity_score, i.is_active) == (4.0, True)
    assert (i.changes_employee_workflows, i.employee_personal_data, i.decisions_on_employees) == (True, "no", "none")
    with Session(engine) as s:
        bt = s.get(BusinessTransaction, i.business_transaction_id)
        assert (bt.bronze_table_name, bt.bronze_id) == (USER_ACTION_TABLE_NAME, first)

    # nothing new -> nothing read; a second submission only adds its own use case
    assert _silver(engine)["read"] == 0
    _submit(engine, "Second", EmployeePersonalData="yes")
    assert _silver(engine) == _counts(read=1, inserted=1)
    second = _initiatives(engine)["Second"]
    assert (second.use_case_id, second.employee_personal_data) == (2, "yes")


def test_business_unit_comes_from_the_owner(engine):
    # same name in two business units -> two use cases, KeyHash = business unit + name
    _submit(engine, "Twin", owner_id=1)
    _submit(engine, "Twin", owner_id=2)
    assert _silver(engine)["inserted"] == 2
    _submit(engine, " twin ", owner_id=1)  # the same name again in ETB -> conflict
    assert _silver(engine) == _counts(read=1, conflicts=1)


def test_lifecycle_approve_detail_and_stage_gate(engine):
    _submit(engine, "Alpha")
    _silver(engine)
    _act(engine, "approve", 1, LeadID=2)
    assert _silver(engine) == _counts(read=1, updated=1)
    alpha = _initiatives(engine)["Alpha"]
    # approving sets the Needs gate date to the decision day (the record's Timestamp)
    assert (alpha.status, alpha.lead_id, alpha.needs_gate_date, alpha.scope_gate_date, alpha.changed_by) == (
        "approved", 2, datetime.datetime(2026, 11, 1, 9, 0), None, "sara")

    # form 2 plus one changed driver: the buckets are recomputed from all actions merged
    _act(engine, "update", 1, AILayer="Operational and advanced AI", EUAIActClass="minimal", ExpectedUsers=40,
         HoursSavedPerCase=1.0, ActualCapex=20_000, MeasuredBenefits=5_000)
    _act(engine, "update", 1, ActualOpex=3_000, Stage="PoC", ScopeGateDate=datetime.datetime(2026, 11, 20),
         DeployGateDate=datetime.datetime(2027, 3, 1))  # deploy gate planned
    assert _silver(engine) == _counts(read=2, updated=2)
    alpha = _initiatives(engine)["Alpha"]
    assert (alpha.ai_layer, alpha.eu_ai_act_class, alpha.expected_users) == ("Operational and advanced AI", "minimal", 40)
    assert alpha.efficiency_score_eur == 3000 * 1.0 * 60  # was 0.5 h per case
    assert alpha.quality_score_eur == 192000  # untouched drivers kept
    assert (alpha.measured_benefits, alpha.actual_costs) == (5_000, 23_000)
    assert (alpha.stage, alpha.needs_gate_date, alpha.scope_gate_date, alpha.deploy_gate_date, alpha.status, alpha.lead_id) == (
        "PoC", datetime.datetime(2026, 11, 1, 9, 0), datetime.datetime(2026, 11, 20), datetime.datetime(2027, 3, 1),
        "approved", 2)

    # every version is a full snapshot; the first stays as it was
    versions = _versions(engine, 1)
    assert [v.status for v in versions] == ["pending", "approved", "approved", "approved"]
    assert versions[0].efficiency_score_eur == 90000 and versions[1].ai_layer is None


def test_name_and_business_unit_cannot_change(engine):
    _submit(engine, "Alpha", owner_id=1)
    _silver(engine)
    _act(engine, "update", 1, Name="Renamed", OwnerID=2, Description="New text")
    _silver(engine)
    alpha = _initiatives(engine)["Alpha"]
    assert (alpha.name, alpha.owner_id, alpha.description) == ("Alpha", 1, "New text")


def test_reject_and_resubmit(engine):
    _submit(engine, "Alpha")
    _silver(engine)
    _act(engine, "reject", 1, Comment="Overlaps with the WFM project")
    _silver(engine)
    alpha = _initiatives(engine)["Alpha"]
    assert (alpha.status, alpha.comment) == ("rejected", "Overlaps with the WFM project")
    _act(engine, "update", 1, Status="pending", Description="Aligned with HR")
    _silver(engine)
    assert _initiatives(engine)["Alpha"].status == "pending"


def test_unchanged_and_refused_actions_are_read_once_and_write_nothing(engine):
    _submit(engine, "Alpha")
    _silver(engine)
    _act(engine, "update", 1, Description="About Alpha")  # the same as before
    _act(engine, "update", 99, Description="x")  # unknown use case
    _act(engine, "approve", 1, LeadID=2)
    _act(engine, "reject", 1, Comment="too late")  # not pending any more
    assert _silver(engine) == _counts(read=4, updated=1, unchanged=1, conflicts=2)
    assert len(_versions(engine, 1)) == 2
    with Session(engine) as s:  # every record has its BusinessTransaction now
        assert s.query(BusinessTransaction).count() == 5
    assert _silver(engine)["read"] == 0


def test_force_recomputes_use_cases_with_user_actions(engine, monkeypatch):
    _submit(engine, "Alpha")
    _submit(engine, "Beta")
    _silver(engine)
    assert _silver(engine, force=True) == _counts(unchanged=2)
    from ai_cockpit_ingestion.transforms import user_input_heuristic
    monkeypatch.setattr(user_input_heuristic, "HOURLY_RATE_EUR", 80)
    assert _silver(engine, force=True) == _counts(updated=2)
    assert _initiatives(engine)["Alpha"].efficiency_score_eur == 3000 * 0.5 * 80


def _sheet_alpha(engine, **over):
    it = SOURCES_BY_KEY["it"]
    row = {c: None for c in it.columns} | {"Name": "Alpha", "Owner": "Owner B", "Department": "Innovation",
                                           "Status": "PoC", "Solution Type": "Custom agent"} | over
    with Session(engine) as s, s.begin():
        stamp = datetime.datetime(2026, 10, 23) + datetime.timedelta(minutes=s.query(BusinessTransaction).count())
        s.execute(insert(EXTRACT_TABLES[it.extract_table]), [row | {"Timestamp": stamp, "SourceFileID": "load.xlsx"}])
    return _silver(engine, source="it")


def test_key_of_a_sheet_initiative_is_a_conflict_and_leaves_it_untouched(engine):
    _sheet_alpha(engine)
    before = _initiatives(engine)["Alpha"]

    _submit(engine, " alpha ", owner_id=2)
    assert _silver(engine) == _counts(read=1, conflicts=1)
    after = _initiatives(engine)["Alpha"]
    assert (after.id, after.stage, after.business_transaction_id) == (before.id, "PoC", before.business_transaction_id)


def test_a_user_action_makes_a_sheet_use_case_ui_owned(engine):
    _sheet_alpha(engine)
    sheet = _initiatives(engine)["Alpha"]
    _act(engine, "update", sheet.use_case_id, Stage="MVP", AILayer="Operational and advanced AI")
    assert _silver(engine)["updated"] == 1
    alpha = _initiatives(engine)["Alpha"]
    # buckets estimated by the sheet heuristic are kept (no base inputs entered in the UI)
    assert (alpha.stage, alpha.ai_layer, alpha.efficiency_score_eur) == ("MVP", "Operational and advanced AI",
                                                                         sheet.efficiency_score_eur)
    # the sheet no longer changes it, and no longer deactivates it
    assert _sheet_alpha(engine, Status="Idea")["ui_owned"] == 1
    it = SOURCES_BY_KEY["it"]
    with Session(engine) as s, s.begin():
        s.execute(insert(EXTRACT_TABLES[it.extract_table]), [{c: None for c in it.columns} | {
            "Name": "Other", "Status": "Idea", "Timestamp": datetime.datetime(2026, 10, 30), "SourceFileID": "x"}])
    assert _silver(engine, source="it")["deactivated"] == 0
    alpha = _initiatives(engine)["Alpha"]
    assert (alpha.stage, alpha.is_active) == ("MVP", True)


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


def test_versions_carry_the_signed_in_users(engine):
    with Session(engine) as s, s.begin():
        s.add_all([AppUser(id=1, email="jonas@demo.local", name="Jonas"),
                   AppUser(id=2, email="sara@demo.local", name="Sara", role="approver")])
    _submit(engine, "Smart Invoice Check", SubmittedByUserID=1)
    _silver(engine)
    use_case_id = _initiatives(engine)["Smart Invoice Check"].use_case_id
    _act(engine, "approve", use_case_id, LeadID=2, SubmittedByUserID=2)
    _silver(engine)
    created, approved = _versions(engine, use_case_id)
    assert (created.created_by_user_id, created.changed_by_user_id) == (1, 1)
    assert (approved.created_by_user_id, approved.changed_by_user_id, approved.status) == (1, 2, "approved")
    with Session(engine) as s:
        assert s.get(AppUser, 1).role == "user" and s.get(Owner, 1).source == "excel"
