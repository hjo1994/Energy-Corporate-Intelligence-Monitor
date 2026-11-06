"""Input form: POST /api/initiatives, pending initiatives and the provisional values
(checked against tests/fixtures/user_input_cases.json, shared with the input orchestration)."""
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.derived import provisional_potential
from app.user_input import RUNNING_COST_RANGES, key_hash, merged, provisional_values, risk_level, running_cost_range

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "user_input_cases.json").read_text())
SNAKE = {
    "CasesPerYear": "cases_per_year", "HoursSavedPerCase": "hours_saved_per_case",
    "ErrorRateBefore": "error_rate_before", "ErrorsAvoided": "errors_avoided", "CostPerError": "cost_per_error",
    "RiskEventsPerYear": "risk_events_per_year", "EventsAvoided": "events_avoided", "CostPerEvent": "cost_per_event",
    "DelayEventsPerYear": "delay_events_per_year", "CostOfDelayPerEvent": "cost_of_delay_per_event",
    "LeadTimeSaved": "lead_time_saved", "EstimateBasis": "estimate_basis",
    "DeliveryLikelihood": "delivery_likelihood", "OneTimeCosts": "one_time_costs",
    "OperatingCosts": "operating_costs", "EmployeePersonalData": "employee_personal_data",
    "PerformanceOrBehaviourControl": "performance_or_behaviour_control",
    "DecisionsOnEmployees": "decisions_on_employees", "ProfilingOfIndividuals": "profiling_of_individuals",
    "ChangesEmployeeWorkflows": "changes_employee_workflows", "ProhibitedPractice": "prohibited_practice",
}


def fixture_input(case):
    return {SNAKE[k]: v for k, v in {**FIXTURE["base"], **case["input"]}.items()}


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=[c["name"] for c in FIXTURE["cases"]])
def test_provisional_values_match_the_shared_fixture(case):
    inputs = fixture_input(case)
    expected = case["expected"]
    assert risk_level(inputs) == expected["riskLevel"]
    if "efficiency" not in expected:
        return
    v = provisional_values(inputs)
    hypothetical = (v["efficiency_score_eur"] + v["quality_score_eur"] + v["risk_reduction_score_eur"]
                    + v["strategic_value_score_eur"])
    actual = {
        "efficiency": v["efficiency_score_eur"], "quality": v["quality_score_eur"],
        "riskReduction": v["risk_reduction_score_eur"], "strategic": v["strategic_value_score_eur"],
        "hypothetical": hypothetical, "confidenceScore": v["confidence_score"], "deliveryScore": v["delivery_score"],
        "potential": provisional_potential(v),
        "oneTimeCosts": v["one_time_costs"], "operatingCosts": v["running_costs"],
        "depreciationYears": v["depreciation_years"],
        "annualCost": v["one_time_costs"] / v["depreciation_years"] + v["running_costs"],
    }
    for key, value in expected.items():
        if key != "riskLevel":
            assert actual[key] == pytest.approx(value), key


def test_merged_drivers_later_values_win():
    first = SimpleNamespace(cases_per_year=100, hours_saved_per_case=1, estimate_basis="rough")
    second = SimpleNamespace(cases_per_year=None, hours_saved_per_case=2, estimate_basis=None)
    assert merged([first, second], ("cases_per_year", "hours_saved_per_case", "estimate_basis")) == {
        "cases_per_year": 100, "hours_saved_per_case": 2, "estimate_basis": "rough"}


def test_running_cost_ranges_round_trip():
    for key, (_, amount) in RUNNING_COST_RANGES.items():
        assert running_cost_range(amount) == key
    assert running_cost_range(10_000) == "up_to_10k" and running_cost_range(10_001) == "10k_to_50k"


def test_key_hash_matches_the_input_orchestration():
    # same normalization: whitespace, non-breaking spaces, zero-width characters, case
    assert key_hash("ETB", " ac_012\xa0 CHECK reporting​ ") == key_hash("ETB", "AC_012 check reporting")
    assert key_hash("IT", "x") != key_hash("ETB", "x")


# --- API ---------------------------------------------------------------------




# all four levers, every number from its domain (app/lifecycle.py):
# 5000 x 0.4 h x 60 € = 120,000; 5000 x 7.5 % x 50 % x 500 € = 93,750; 3 x 25 % x 30,000 € = 22,500;
# 12 x 150,000 € x 10 % = 180,000 -> 416,250 hypothetical, x 0.6 x 0.65 = 162,337.5 potential
FORM1_VALUES = {
    "cases_per_year": 5000, "hours_saved_per_case": 0.4, "error_rate_before": 0.075, "errors_avoided": 0.5,
    "cost_per_error": 500, "risk_events_per_year": 3, "events_avoided": 0.25, "cost_per_event": 30000,
    "delay_events_per_year": 12, "cost_of_delay_per_event": 150000, "lead_time_saved": 0.1,
    "one_time_costs": 175000,
}


def form1(**over):
    values = {**fixture_input(FIXTURE["cases"][0]), **FORM1_VALUES}
    values.pop("operating_costs")
    return {
        "name": "Smart Invoice Check", "description": "Checks invoices against orders",
        "value_type_id": 1, "ai_layer": "AI for business process optimization", "stage": "Ideation",
        "date_delivery": "Q3 2027", **values, "running_cost_range": "10k_to_50k",
        "solution_complexity_score": 4, **over,
    }


@pytest.fixture()
def submit(client):
    return lambda **over: client.post("/api/initiatives", json=form1(**over))


def test_post_stores_a_create_action_and_returns_it_pending(submit, db_path):
    resp = submit()
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending" and body["id"] == -body["user_input_id"]
    assert (body["processing"], body["approval_status"], body["provisional"]) == ("pending", "pending", True)
    assert body["owner"]["name"] == "Lead C" and body["date_delivery"].startswith("2027-07-01")
    assert body["ai_layer"] == "AI for business process optimization" and body["solution_type"] is None
    # 10k-50k range -> 30,000 entered, x 0.65 expected: annual cost = 175,000 x 0.65 / 5 + 19,500
    assert body["running_costs"] == pytest.approx(19_500)
    assert body["potential_value_eur"] == pytest.approx(162_337.5)
    assert body["annual_cost_eur"] == pytest.approx(42_250)
    assert body["risk_classification"]["id"] == 2
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            'SELECT "ActionType", "UseCaseID", "Name", "SubmittedBy", "SourceFileID", "OwnerID", "OperatingCosts",'
            ' "AILayer" FROM "UserActionExtracts"'
        ).fetchall()
    assert row == [("create", None, "Smart Invoice Check", "Dev User", "user-input", 3, 30000.0,
                    "AI for business process optimization")]


def test_pending_initiatives_are_listed_after_the_others_and_follow_filters(submit, client):
    submit()
    resp = client.get("/api/initiatives", params={"limit": 500})
    items = resp.json()["items"]
    assert resp.json()["total"] == 5 and items[-1]["name"] == "Smart Invoice Check"
    assert [i["status"] for i in items] == ["active"] * 4 + ["pending"]
    assert client.get("/api/initiatives", params={"business_unit": "IT"}).json()["total"] == 1
    assert client.get("/api/initiatives", params={"business_unit": "ETB"}).json()["total"] == 3
    assert client.get("/api/initiatives", params={"include_pending": False}).json()["total"] == 4
    assert client.get("/api/initiatives", params={"approval_status": "pending"}).json()["total"] == 1
    # paging over both stays consistent
    pages = [client.get("/api/initiatives", params={"limit": 2, "offset": o}).json()["items"] for o in (0, 2, 4)]
    assert [i["name"] for p in pages for i in p] == [i["name"] for i in items]
    pending_id = items[-1]["id"]
    assert client.get(f"/api/initiatives/{pending_id}").json()["name"] == "Smart Invoice Check"


def test_duplicate_name_in_the_same_business_unit_is_409(submit, db_path):
    # the fixture's keys are placeholders; give Alpha and Omega (both ETB) their real keys
    with sqlite3.connect(db_path) as conn:
        for name in ("Alpha", "Omega"):
            conn.execute('UPDATE "Initiative" SET "KeyHash" = ? WHERE "Name" = ?', (key_hash("ETB", name), name))
    assert submit(name="alpha").status_code == 409  # existing use case in ETB (the user is owner Lead C)
    assert submit(name="New one").status_code == 201
    assert submit(name=" NEW  one ").status_code == 409  # still pending
    assert submit(name="Omega").status_code == 409  # inactive use cases keep their key
    with sqlite3.connect(db_path) as conn:  # a user who is no owner yet, in IT
        conn.execute('UPDATE "Owner" SET "UserID" = NULL WHERE "ID" = 3')
    assert submit(name="Alpha", business_unit="IT").status_code == 201  # other business unit


@pytest.mark.parametrize(
    "over",
    [
        {"stage": "Pilot"}, {"date_start": "2027-01-01"}, {"error_rate_before": 8},
        {"cases_per_year": -1}, {"cases_per_year": 3000}, {"one_time_costs": 200000}, {"lead_time_saved": 0.15},
        {"estimate_basis": "guess"}, {"solution_complexity_score": 10},
        {"employee_personal_data": "maybe"}, {"name": "   "}, {"one_time_costs": None},
        {"unknown_field": 1}, {"ai_layer": "Some AI"}, {"ai_layer": None}, {"running_cost_range": "5k"},
        {"operating_costs": 1000},  # replaced by the range
        # no complete lever
        {"cases_per_year": None, "risk_events_per_year": None, "delay_events_per_year": None},
        {"owner_id": 99}, {"value_type_id": 99},
    ],
)
def test_invalid_input_is_422(submit, over):
    assert submit(**over).status_code == 422


def test_post_requires_authentication(client, monkeypatch):
    monkeypatch.setenv("EG_AUTH_DEV_MODE", "false")
    assert client.post("/api/initiatives", json={}).status_code == 401


def test_missing_user_action_table_means_no_pending_and_post_503(client, db_path):
    # e.g. Backend deployed before the input orchestration has created the table
    with sqlite3.connect(db_path) as conn:
        conn.execute('DROP TABLE "UserActionExtracts"')
    resp = client.get("/api/initiatives", params={"limit": 500})
    assert resp.status_code == 200 and resp.json()["total"] == 4
    assert client.get("/api/initiatives/1").status_code == 200
    post = client.post("/api/initiatives", json=form1())
    assert post.status_code == 503 and "not available yet" in post.json()["detail"]


def test_read_only_database_gives_a_clear_503(client, db_path, monkeypatch):
    # A read-only file (chmod) does not stop root, so the write engine is made read-only instead.
    import sqlite3 as sq
    from urllib.parse import quote

    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    uri = f"file:{quote(str(db_path))}?mode=ro"
    client.app.state.write_engine = create_engine(
        "sqlite://", creator=lambda: sq.connect(uri, uri=True, check_same_thread=False), poolclass=NullPool)
    resp = client.post("/api/initiatives", json=form1())
    assert resp.status_code == 503 and "read-only" in resp.json()["detail"]


def test_feature_switch(client, submit, monkeypatch):
    assert client.get("/api/features").json() == {"initiative_input": True}
    monkeypatch.setenv("AI_COCKPIT_ENABLE_INITIATIVE_INPUT", "false")
    assert client.get("/api/features").json() == {"initiative_input": False}
    assert submit().status_code == 403


def test_the_signed_in_user_becomes_the_owner(submit, client, db_path):
    def owners():
        with sqlite3.connect(db_path) as conn:
            return conn.execute('SELECT "ID", "Name", "Category", "UserID", "Source" FROM "Owner" ORDER BY "ID"').fetchall()

    with sqlite3.connect(db_path) as conn:
        conn.execute('UPDATE "Owner" SET "UserID" = NULL WHERE "ID" = 3')
    assert client.get("/api/auth/rights").json()["owner"] is None
    # no owner yet: form 1 asks for the business unit
    resp = submit(name="First")
    assert resp.status_code == 422 and "business unit" in resp.json()["detail"]
    resp = submit(name="First", business_unit="IT")
    assert resp.status_code == 201 and resp.json()["owner"]["name"] == "Dev User"
    assert owners()[-1] == (4, "Dev User", "IT", 1, "app")
    # from now on always that owner, whatever business unit is sent
    assert submit(name="Second", business_unit="ETB").json()["owner"]["id"] == 4
    assert client.get("/api/auth/rights").json()["owner"] == {"id": 4, "name": "Dev User", "category": "IT"}
    mine = client.get("/api/me/use-cases").json()
    assert {m["name"] for m in mine} >= {"First", "Second"}
    with sqlite3.connect(db_path) as conn:
        assert conn.execute('SELECT DISTINCT "SubmittedByUserID" FROM "UserActionExtracts"').fetchall() == [(1,)]


def test_an_excel_owner_of_the_same_name_is_linked(submit, db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute('UPDATE "Owner" SET "UserID" = NULL WHERE "ID" = 3')
        conn.execute('UPDATE "Owner" SET "Name" = \'dev user\' WHERE "ID" = 2')  # Excel owner in IT
    resp = submit(name="Linked")
    assert resp.status_code == 201 and resp.json()["owner"]["id"] == 2
    with sqlite3.connect(db_path) as conn:
        assert conn.execute('SELECT "UserID", "Source" FROM "Owner" WHERE "ID" = 2').fetchone() == (1, "excel")


def test_an_owner_can_be_chosen(submit, client, db_path):
    """Form 1 can name any owner; the submitter still sees the use case as theirs."""
    resp = submit(name="For Owner B", owner_id=2)
    assert resp.status_code == 201, resp.text
    assert (resp.json()["owner"]["id"], resp.json()["owner"]["category"]) == (2, "IT")
    with sqlite3.connect(db_path) as conn:
        assert conn.execute('SELECT "OwnerID", "SubmittedByUserID" FROM "UserActionExtracts"').fetchall() == [(2, 1)]
    assert "For Owner B" in {m["name"] for m in client.get("/api/me/use-cases").json()}
    # the same name in another business unit is another use case; in the same one a duplicate
    assert submit(name="For Owner B").status_code == 201  # Lead C, ETB
    assert submit(name="For Owner B", owner_id=2).status_code == 409
    assert submit(name="Nobody", owner_id=99).status_code == 422


def test_former_stages_are_mapped_to_ideation(submit, db_path):
    assert submit(name="Old stage", stage="Exploration").json()["stage"] == "Ideation"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute('SELECT "Stage" FROM "UserActionExtracts"').fetchall() == [("Ideation",)]


def test_form1_without_stage_is_ideation(client):
    body = form1(name="No stage")
    body.pop("stage")
    resp = client.post("/api/initiatives", json=body)
    assert resp.status_code == 201, resp.text
    assert resp.json()["stage"] == "Ideation"
