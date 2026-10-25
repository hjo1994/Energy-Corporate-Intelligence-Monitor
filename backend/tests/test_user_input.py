"""Input form: POST /api/initiatives, pending initiatives and the provisional values
(checked against tests/fixtures/user_input_cases.json, shared with the input orchestration)."""
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.user_input import key_hash, provisional_values, risk_level

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
    record = SimpleNamespace(**fixture_input(case))
    expected = case["expected"]
    assert risk_level(record) == expected["riskLevel"]
    if "efficiency" not in expected:
        return
    v = provisional_values(record)
    hypothetical = (v["efficiency_score_eur"] + v["quality_score_eur"] + v["risk_reduction_score_eur"]
                    + v["strategic_value_score_eur"])
    actual = {
        "efficiency": v["efficiency_score_eur"], "quality": v["quality_score_eur"],
        "riskReduction": v["risk_reduction_score_eur"], "strategic": v["strategic_value_score_eur"],
        "hypothetical": hypothetical, "confidenceScore": v["confidence_score"], "deliveryScore": v["delivery_score"],
        "potential": hypothetical * v["confidence_score"] * v["delivery_score"],
        "oneTimeCosts": v["one_time_costs"], "operatingCosts": v["operating_costs"],
        "depreciationYears": v["depreciation_years"],
        "annualCost": v["one_time_costs"] / v["depreciation_years"] + v["operating_costs"],
    }
    for key, value in expected.items():
        if key != "riskLevel":
            assert actual[key] == pytest.approx(value), key


def test_key_hash_matches_the_input_orchestration():
    # same normalization: whitespace, non-breaking spaces, zero-width characters, case
    assert key_hash("ETB", " ac_012\xa0 CHECK reporting​ ") == key_hash("ETB", "AC_012 check reporting")
    assert key_hash("IT", "x") != key_hash("ETB", "x")


# --- API ---------------------------------------------------------------------


@pytest.fixture()
def submit(client):
    def post(**over):
        body = {
            "name": "Smart Invoice Check", "description": "Checks invoices against orders",
            "owner_id": 1, "value_type_id": 1, "solution_type_id": 1, "stage": "Idea",
            "date_delivery": "Q3 2027",
            **fixture_input(FIXTURE["cases"][0]),
            "solution_complexity_score": 4,
            **over,
        }
        return client.post("/api/initiatives", json=body)

    return post


def test_post_stores_the_record_and_returns_it_pending(submit, db_path):
    resp = submit()
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending" and body["id"] == -body["user_input_id"]
    assert body["owner"]["name"] == "Owner A" and body["date_delivery"].startswith("2027-07-01")
    assert body["potential_value_eur"] == pytest.approx(187980)
    assert body["annual_cost_eur"] == pytest.approx(58500)
    assert body["risk_classification"]["id"] == 2
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            'SELECT "Name", "SubmittedBy", "SourceFileID", "OwnerID" FROM "UserInput_Initiatives_Extract"'
        ).fetchall()
    assert row == [("Smart Invoice Check", "Dev User", "user-input", 1)]


def test_pending_initiatives_are_listed_after_the_others_and_follow_filters(submit, client):
    submit()
    resp = client.get("/api/initiatives", params={"limit": 500})
    items = resp.json()["items"]
    assert resp.json()["total"] == 5 and items[-1]["name"] == "Smart Invoice Check"
    assert [i["status"] for i in items] == ["active"] * 4 + ["pending"]
    assert client.get("/api/initiatives", params={"business_unit": "IT"}).json()["total"] == 1
    assert client.get("/api/initiatives", params={"business_unit": "ETB"}).json()["total"] == 3
    assert client.get("/api/initiatives", params={"include_pending": False}).json()["total"] == 4
    # paging over both stays consistent
    pages = [client.get("/api/initiatives", params={"limit": 2, "offset": o}).json()["items"] for o in (0, 2, 4)]
    assert [i["name"] for p in pages for i in p] == [i["name"] for i in items]


def test_duplicate_name_in_the_same_business_unit_is_409(submit, db_path):
    # the fixture's keys are placeholders; give Alpha and Omega (both ETB) their real keys
    with sqlite3.connect(db_path) as conn:
        for name in ("Alpha", "Omega"):
            conn.execute('UPDATE "Initiative" SET "KeyHash" = ? WHERE "Name" = ?', (key_hash("ETB", name), name))
    assert submit(name="alpha").status_code == 409  # existing silver initiative in ETB
    assert submit(name="Alpha", owner_id=2).status_code == 201  # other business unit (IT)
    assert submit(name="New one").status_code == 201
    assert submit(name=" NEW  one ").status_code == 409  # still pending
    assert submit(name="Omega").status_code == 409  # inactive initiatives keep their key


@pytest.mark.parametrize(
    "over",
    [
        {"stage": "Pilot"}, {"date_start": "2027-01-01"}, {"error_rate_before": 8},
        {"cases_per_year": -1}, {"estimate_basis": "guess"}, {"solution_complexity_score": 10},
        {"employee_personal_data": "maybe"}, {"name": "   "}, {"one_time_costs": None},
        {"unknown_field": 1},
        # no complete lever
        {"cases_per_year": None, "risk_events_per_year": None, "delay_events_per_year": None},
        {"owner_id": 99}, {"value_type_id": 99}, {"solution_type_id": 99},
    ],
)
def test_invalid_input_is_422(submit, over):
    assert submit(**over).status_code == 422


def test_post_requires_authentication(client, monkeypatch):
    monkeypatch.setenv("EG_AUTH_DEV_MODE", "false")
    assert client.post("/api/initiatives", json={}).status_code == 401
