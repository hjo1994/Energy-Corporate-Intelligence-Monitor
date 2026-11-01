"""Use-case endpoints: forms 1 and 2, my use cases, approvals and decisions.

The pipeline is not part of these tests: `process` stands in for
bronze_to_silver_user_input turning a create record into the first silver
version; everything else is shown through the overlay of unprocessed actions."""
import sqlite3

import pytest

from app.user_input import key_hash
from tests.test_user_input import form1


@pytest.fixture()
def submit(client):
    def post(**over):
        resp = client.post("/api/initiatives", json=form1(**over))
        assert resp.status_code == 201, resp.text
        return resp.json()

    return post


def process(db_path, record_id, use_case_id):
    """What the DAG does with a create: BusinessTransaction + first silver version (pending)."""
    conn = sqlite3.connect(db_path)
    name, owner_id = conn.execute(
        'SELECT "Name", "OwnerID" FROM "UserActionExtracts" WHERE "ID" = ?', (record_id,)).fetchone()
    bt = conn.execute('INSERT INTO "BusinessTransaction"("BronzeID", "BronzeTableName") VALUES (?, ?)',
                      (record_id, "UserActionExtracts")).lastrowid
    conn.execute(
        'INSERT INTO "Initiative"("UseCaseID", "Name", "Description", "Stage", "Status", "OwnerID", "ValueTypeID",'
        ' "AILayer", "EfficiencyScoreEur", "QualityScoreEur", "RiskReductionScoreEur", "StrategicValueScoreEur",'
        ' "ConfidenceScore", "DeliveryScore", "OneTimeCosts", "RunningCosts", "DepreciationYears",'
        ' "SolutionComplexityScore", "EmployeePersonalData", "PerformanceOrBehaviourControl", "DecisionsOnEmployees",'
        ' "ProfilingOfIndividuals", "ChangesEmployeeWorkflows", "ProhibitedPractice", "KeyHash", "RowHash",'
        ' "IsActive", "BusinessTransactionID", "ChangedBy", "Timestamp")'
        " VALUES (?, ?, 'Checks invoices against orders', 'Idea', 'pending', ?, 1, 'AI for business process"
        " optimization', 90000, 192000, 50000, 150000, 0.6, 0.65, 130000, 19500, 5, 4, 'no', 0, 'none', 0, 1, 0,"
        " ?, 'r', 1, ?, 'Dev User', '2026-10-25 13:01:00')",
        (use_case_id, name, owner_id, key_hash("ETB", name), bt),
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def idea(client, submit, db_path):
    """An idea submitted by the signed-in user and processed into use case 6."""
    created = submit()
    process(db_path, created["user_input_id"], 6)
    return 6


def detail(client, id):
    resp = client.get(f"/api/use-cases/{id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_form_options(client):
    options = client.get("/api/form-options").json()
    assert [o["value"] for o in options["running_cost_ranges"]] == ["up_to_10k", "10k_to_50k", "50k_to_100k",
                                                                    "over_100k"]
    assert options["running_cost_ranges"][1]["amount"] == 30000
    assert "Operational and advanced AI" in [o["value"] for o in options["ai_layers"]]
    assert {"enabling_teams", "eu_ai_act_classes", "stagegates", "applicable_to"} <= set(options)


def test_sheet_use_case_detail(client):
    alpha = detail(client, 1)
    assert (alpha["name"], alpha["version_id"], alpha["revision"], alpha["processing"]) == ("Alpha", 2, "2-0",
                                                                                            "assessed")
    assert alpha["approval_status"] is None and alpha["drivers"] == {} and alpha["pending_action_ids"] == []
    assert alpha["form2_progress"] == {"filled": 1, "total": 18}  # solution type only
    assert (alpha["can_edit"], alpha["can_decide"]) == (False, False)  # Dev User is not Owner A
    assert client.get("/api/use-cases/99").status_code == 404


def test_only_submitter_owner_lead_or_admin_may_edit(client, monkeypatch):
    patch = {"base_revision": "2-0", "description": "New"}
    assert client.patch("/api/use-cases/1", json=patch).status_code == 403
    monkeypatch.setenv("EG_AUTH_DEV_GROUPS", '["ai_cockpit_admins"]')
    assert detail(client, 1)["can_edit"] is True
    resp = client.patch("/api/use-cases/1", json=patch)
    assert resp.status_code == 200, resp.text
    alpha = resp.json()
    # the change shows at once, marked as not processed yet; the sheet use case is now maintained in the UI
    assert (alpha["description"], alpha["processing"], alpha["provisional"]) == ("New", "changes_pending", True)
    assert alpha["revision"] != "2-0" and len(alpha["pending_action_ids"]) == 1
    # buckets estimated from the sheet are kept: no value inputs entered
    assert alpha["potential_value_eur"] == pytest.approx(54000)


def test_a_pending_idea_can_be_read_but_not_changed(client, submit, as_approver):
    created = submit()
    pending = detail(client, created["id"])
    assert (pending["processing"], pending["approval_status"], pending["can_edit"]) == ("pending", "pending", False)
    assert pending["drivers"]["cases_per_year"] == 3000 and pending["running_cost_range"] == "10k_to_50k"
    assert client.patch(f"/api/use-cases/{created['id']}", json={"base_revision": "0-1", "stage": "PoC"}
                        ).status_code == 409
    assert client.post(f"/api/use-cases/{created['id']}/decision",
                       json={"decision": "approve", "lead_id": 3}).status_code == 409
    inbox = client.get("/api/approvals").json()
    assert [(i["name"], i["can_decide"]) for i in inbox] == [("Smart Invoice Check", False)]


def test_my_use_cases_with_roles_and_todos(client, idea, db_path):
    conn = sqlite3.connect(db_path)
    conn.execute('UPDATE "Initiative" SET "LeadID" = 3 WHERE "UseCaseID" = 2')  # Dev User = Lead C (e-mail)
    conn.commit()
    conn.close()
    mine = {u["name"]: u for u in client.get("/api/me/use-cases").json()}
    assert set(mine) == {"Smart Invoice Check", "Beta"}
    assert mine["Smart Invoice Check"]["roles"] == ["submitter"]
    assert mine["Smart Invoice Check"]["approval_status"] == "pending" and mine["Beta"]["roles"] == ["lead"]


def test_lifecycle_approve_then_form2(client, idea, as_approver, monkeypatch):
    inbox = client.get("/api/approvals").json()
    assert [(i["id"], i["can_decide"], i["submitted_by"]) for i in inbox] == [(6, True, "Dev User")]
    before = detail(client, 6)
    assert (before["processing"], before["can_decide"]) == ("not_assessed", True)  # gold has not run yet

    # form 2 opens only after approval
    assert client.patch("/api/use-cases/6", json={"base_revision": before["revision"],
                                                  "enabling_team": "EL.AI"}).status_code == 409
    assert client.post("/api/use-cases/6/decision", json={"decision": "approve"}).status_code == 422  # no lead
    resp = client.post("/api/use-cases/6/decision",
                       json={"decision": "approve", "lead_id": 3, "needs_gate_passed_at": "2026-10-31"})
    assert resp.status_code == 200, resp.text
    approved = resp.json()
    assert (approved["approval_status"], approved["stagegate"], approved["passed_at"]) == (
        "approved", "Needs", "2026-10-31T00:00:00")
    assert approved["lead"]["name"] == "Lead C" and approved["todos"] == ["complete_details"]
    assert client.get("/api/approvals").json() == []
    assert client.post("/api/use-cases/6/decision",
                       json={"decision": "reject", "comment": "late"}).status_code == 409  # not pending any more

    # a stale revision is refused instead of overwriting
    stale = client.patch("/api/use-cases/6", json={"base_revision": before["revision"], "enabling_team": "EL.AI"})
    assert stale.status_code == 409 and stale.json()["detail"]["revision"] == approved["revision"]

    resp = client.patch("/api/use-cases/6", json={
        "base_revision": approved["revision"], "enabling_team": "EL.AI", "eu_ai_act_class": "minimal",
        "applicable_to": ["ETB", "50Hertz", "ETB"], "expected_users": 40, "solution_type_id": 1,
        "hours_saved_per_case": 1.0, "stagegate": "Scope", "passed_at": "2026-12-01", "actual_capex": 20000,
        "actual_opex": 3000, "measured_benefits": 5000,
    })
    assert resp.status_code == 200, resp.text
    uc = resp.json()
    assert (uc["enabling_team"], uc["applicable_to"], uc["expected_users"]) == ("EL.AI", "ETB,50Hertz", 40)
    assert (uc["stagegate"], uc["approval_status"], uc["actual_costs"]) == ("Scope", "approved", 23000)
    # value recomputed provisionally from all actions merged: 3000 cases x 1 h x 60 €
    assert uc["efficiency_score_eur"] == 180000 and uc["quality_score_eur"] == 192000
    assert uc["drivers"]["hours_saved_per_case"] == 1.0 and uc["drivers"]["cases_per_year"] == 3000
    assert uc["form2_progress"]["filled"] == 7


def test_name_and_business_unit_cannot_change(client, idea):
    revision = detail(client, 6)["revision"]
    assert client.patch("/api/use-cases/6", json={"base_revision": revision, "name": "Renamed"}).status_code == 422
    resp = client.patch("/api/use-cases/6", json={"base_revision": revision, "owner_id": 2})  # IT
    assert resp.status_code == 422 and "business unit" in resp.json()["detail"]
    assert client.patch("/api/use-cases/6", json={"base_revision": revision, "owner_id": 3}).status_code == 200
    assert client.patch("/api/use-cases/6", json={"base_revision": "x"}).status_code == 409


def test_reject_and_resubmit(client, idea, as_approver):
    assert client.post("/api/use-cases/6/decision", json={"decision": "reject"}).status_code == 422  # no comment
    rejected = client.post("/api/use-cases/6/decision",
                           json={"decision": "reject", "comment": "Overlaps with WFM"}).json()
    assert (rejected["approval_status"], rejected["comment"], rejected["todos"]) == (
        "rejected", "Overlaps with WFM", ["revise_and_resubmit"])
    resp = client.patch("/api/use-cases/6", json={"base_revision": rejected["revision"], "resubmit": True,
                                                  "description": "Aligned with HR"})
    assert resp.status_code == 200 and resp.json()["approval_status"] == "pending"


def test_approver_endpoints_need_the_right(client, idea):
    assert client.get("/api/approvals").status_code == 403
    assert client.get("/api/use-cases/6/similar").status_code == 403
    assert client.post("/api/use-cases/6/decision", json={"decision": "approve", "lead_id": 3}).status_code == 403


def test_similar_use_cases(client, submit, db_path, as_approver):
    created = submit(name="Invoice automation", description="Automation of invoice checks against orders")
    process(db_path, created["user_input_id"], 6)
    similar = client.get("/api/use-cases/1/similar").json()  # Alpha: "100% automation"
    assert [s["name"] for s in similar] == ["Invoice automation"] and 0 < similar[0]["score"] < 1


def test_stage_needs_its_gate(client, submit, idea, as_approver):
    # a new idea has passed no gate: PoC and later are refused
    resp = client.post("/api/initiatives", json=form1(name="Too early", stage="PoC"))
    assert resp.status_code == 422 and "scope gate" in resp.text

    approved = client.post("/api/use-cases/6/decision", json={"decision": "approve", "lead_id": 3}).json()
    resp = client.patch("/api/use-cases/6", json={"base_revision": approved["revision"], "stage": "PoC"})
    assert resp.status_code == 422 and resp.json()["detail"] == "Stage PoC needs the scope gate to be passed first."

    # the gate passed in the same save counts; production still needs the deploy gate
    resp = client.patch("/api/use-cases/6", json={"base_revision": approved["revision"], "stage": "MVP",
                                                  "stagegate": "Scope", "passed_at": "2026-12-01"})
    assert resp.status_code == 200, resp.text
    scoped = resp.json()
    assert (scoped["stage"], scoped["stagegate"]) == ("MVP", "Scope")
    resp = client.patch("/api/use-cases/6", json={"base_revision": scoped["revision"], "stage": "Production"})
    assert resp.status_code == 422 and "deploy gate" in resp.json()["detail"]
    resp = client.patch("/api/use-cases/6", json={"base_revision": scoped["revision"], "stage": "Production",
                                                  "stagegate": "Deploy", "passed_at": "2027-03-01"})
    assert resp.status_code == 200 and resp.json()["stage"] == "Production"
