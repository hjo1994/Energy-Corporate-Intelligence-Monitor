"""Use-case endpoints: forms 1 and 2, my use cases, approvals and decisions.

The pipeline is not part of these tests: `process` stands in for
bronze_to_silver_user_input turning a create record into the first silver
version; everything else is shown through the overlay of unprocessed actions."""
import datetime
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
    assert options["stage_gate_rules"]["PoC"] == {"passed": ["Scope"], "not_passed": ["Deploy"]}
    assert options["stage_order"][:3] == ["Idea", "Exploration", "PoC"] and options["stage_order"][-1] == "Retired"
    assert "Retired" in [o["value"] for o in options["stages"]]
    assert options["value_domains"]["one_time_costs"][0] == {"value": 25000, "label": "under 50k €"}
    assert set(options["value_domains"]) >= {"cases_per_year", "hours_saved_per_case", "lead_time_saved"}


def test_sheet_use_case_detail(client):
    alpha = detail(client, 1)
    assert (alpha["name"], alpha["version_id"], alpha["revision"], alpha["processing"]) == ("Alpha", 2, "2-0",
                                                                                            "assessed")
    assert alpha["approval_status"] is None and alpha["drivers"] == {} and alpha["pending_action_ids"] == []
    assert alpha["form2_progress"] == {"filled": 1, "total": 18}  # solution type only
    assert (alpha["can_edit"], alpha["can_decide"]) == (False, False)  # Dev User is not Owner A
    assert client.get("/api/use-cases/99").status_code == 404


def test_only_submitter_owner_lead_or_admin_may_edit(client, monkeypatch):
    patch = {"base_revision": "2-0", "value_domain": "New"}
    assert client.patch("/api/use-cases/1", json=patch).status_code == 403
    monkeypatch.setenv("EG_AUTH_DEV_GROUPS", '["ai_cockpit_admins"]')
    assert detail(client, 1)["can_edit"] is True
    resp = client.patch("/api/use-cases/1", json=patch)
    assert resp.status_code == 200, resp.text
    alpha = resp.json()
    # the change shows at once, marked as not processed yet; the sheet use case is now maintained in the UI
    assert (alpha["value_domain"], alpha["processing"], alpha["provisional"]) == ("New", "changes_pending", True)
    assert alpha["revision"] != "2-0" and len(alpha["pending_action_ids"]) == 1
    # buckets estimated from the sheet are kept: no value inputs entered
    assert alpha["potential_value_eur"] == pytest.approx(54000)


def test_a_pending_idea_can_be_read_but_not_changed(client, submit, as_approver):
    created = submit()
    pending = detail(client, created["id"])
    assert (pending["processing"], pending["approval_status"], pending["can_edit"]) == ("pending", "pending", False)
    assert pending["drivers"]["cases_per_year"] == 5000 and pending["running_cost_range"] == "10k_to_50k"
    assert client.patch(f"/api/use-cases/{created['id']}", json={"base_revision": "0-1", "stage": "PoC"}
                        ).status_code == 409
    assert client.post(f"/api/use-cases/{created['id']}/decision",
                       json={"decision": "approve", "lead_id": 3}).status_code == 409
    inbox = client.get("/api/approvals").json()
    assert [(i["name"], i["can_decide"]) for i in inbox] == [("Smart Invoice Check", False)]


def test_my_use_cases_with_roles_and_todos(client, idea, db_path):
    conn = sqlite3.connect(db_path)
    conn.execute('UPDATE "Initiative" SET "LeadID" = 3 WHERE "UseCaseID" = 2')  # Dev User = Lead C (Owner.UserID)
    conn.commit()
    conn.close()
    mine = {u["name"]: u for u in client.get("/api/me/use-cases").json()}
    assert set(mine) == {"Smart Invoice Check", "Beta"}
    assert mine["Smart Invoice Check"]["roles"] == ["submitter", "owner"]  # the submitter is the owner
    assert mine["Smart Invoice Check"]["approval_status"] == "pending" and mine["Beta"]["roles"] == ["lead"]


def test_lifecycle_approve_then_form2(client, idea, as_approver, monkeypatch):
    inbox = client.get("/api/approvals").json()
    assert [(i["id"], i["can_decide"], i["submitted_by"]) for i in inbox] == [(6, True, "Dev User")]
    before = detail(client, 6)
    assert (before["processing"], before["can_decide"]) == ("not_assessed", True)  # gold has not run yet

    # form 2 can be filled in at any time, also before the approval
    resp = client.patch("/api/use-cases/6", json={"base_revision": before["revision"], "enabling_team": "EL.AI"})
    assert resp.status_code == 200, resp.text
    before = resp.json()
    assert client.post("/api/use-cases/6/decision", json={"decision": "approve"}).status_code == 422  # no lead
    assert client.post("/api/use-cases/6/decision", json={"decision": "approve", "lead_id": 3,
                                                          "needs_gate_passed_at": "2026-10-31"}).status_code == 422
    resp = client.post("/api/use-cases/6/decision", json={"decision": "approve", "lead_id": 3})
    assert resp.status_code == 200, resp.text
    approved = resp.json()
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    # approving passes the needs gate today
    assert (approved["approval_status"], approved["needs_gate_date"], approved["last_gate"]) == (
        "approved", f"{today}T00:00:00", "Needs")
    # form 2 was saved before the approval, so no to-do: empty fields only show in the progress
    assert approved["lead"]["name"] == "Lead C" and approved["todos"] == []
    assert client.get("/api/approvals").json() == []
    assert client.post("/api/use-cases/6/decision",
                       json={"decision": "reject", "comment": "late"}).status_code == 409  # not pending any more

    # a stale revision is refused instead of overwriting
    stale = client.patch("/api/use-cases/6", json={"base_revision": before["revision"], "enabling_team": "DiY"})
    assert stale.status_code == 409 and stale.json()["detail"]["revision"] == approved["revision"]

    resp = client.patch("/api/use-cases/6", json={
        "base_revision": approved["revision"], "eu_ai_act_class": "minimal",
        "applicable_to": ["ETB", "50Hertz", "ETB"], "expected_users": 40, "solution_type_id": 1,
        "hours_saved_per_case": 2.5, "scope_gate_date": "2030-03-01", "actual_capex": 20000,
        "actual_opex": 3000, "measured_benefits": 5000,
    })
    assert resp.status_code == 200, resp.text
    uc = resp.json()
    assert (uc["enabling_team"], uc["applicable_to"], uc["expected_users"]) == ("EL.AI", "ETB,50Hertz", 40)
    assert (uc["scope_gate_date"], uc["last_gate"], uc["approval_status"], uc["actual_costs"]) == (
        "2030-03-01T00:00:00", "Needs", "approved", 23000)  # a planned gate is not passed
    # value recomputed provisionally from all actions merged: 5000 cases x 2.5 h x 60 €
    assert uc["efficiency_score_eur"] == 750000 and uc["quality_score_eur"] == 93750
    assert uc["drivers"]["hours_saved_per_case"] == 2.5 and uc["drivers"]["cases_per_year"] == 5000
    assert uc["form2_progress"]["filled"] == 7


def test_complete_details_until_form2_saved(client, idea, as_approver):
    resp = client.post("/api/use-cases/6/decision", json={"decision": "approve", "lead_id": 3})
    assert resp.status_code == 200 and resp.json()["todos"] == ["complete_details"]
    mine = {u["id"]: u for u in client.get("/api/me/use-cases").json()}
    assert mine[6]["todos"] == ["complete_details"]
    # a stage change alone does not complete the details
    assert patch(client, 6, stage="On hold").json()["todos"] == ["complete_details"]
    uc = patch(client, 6, enabling_team="EL.AI").json()
    assert uc["todos"] == [] and uc["form2_progress"]["filled"] < uc["form2_progress"]["total"]
    mine = {u["id"]: u for u in client.get("/api/me/use-cases").json()}
    assert mine[6]["todos"] == []


def patch(client, id, **fields):
    return client.patch(f"/api/use-cases/{id}", json={"base_revision": detail(client, id)["revision"], **fields})


def test_stage_and_gate_dates_must_fit(client, idea):
    # PoC needs the scope gate passed (form 2 Excel: "scope gate must be passed before PoC")
    resp = patch(client, 6, stage="PoC")
    assert resp.status_code == 422 and "scope gate" in resp.json()["detail"]
    assert patch(client, 6, stage="PoC", scope_gate_date="2030-01-01").status_code == 422  # in the future
    resp = patch(client, 6, stage="PoC", needs_gate_date="2026-02-01", scope_gate_date="2026-03-01",
                 deploy_gate_date="2030-06-01")
    assert resp.status_code == 200, resp.text
    uc = resp.json()
    assert (uc["stage"], uc["last_gate"], uc["stage_problems"]) == ("PoC", "Scope", [])
    # in PoC the deploy gate is not passed yet
    resp = patch(client, 6, deploy_gate_date="2026-04-01")
    assert resp.status_code == 422 and "deploy gate" in resp.json()["detail"]
    # gates in order
    resp = patch(client, 6, scope_gate_date="2026-01-01")
    assert resp.status_code == 422 and "before the needs gate" in resp.json()["detail"]
    # Production needs the deploy gate passed too
    assert patch(client, 6, stage="Production").status_code == 422
    resp = patch(client, 6, stage="Production", deploy_gate_date="2026-05-01")
    assert resp.status_code == 200 and resp.json()["last_gate"] == "Deploy"
    # back to an earlier stage: the scope and deploy gates must move to the future
    assert patch(client, 6, stage="Exploration").status_code == 422
    resp = patch(client, 6, stage="Exploration", scope_gate_date="2030-01-01", deploy_gate_date="2030-06-01")
    assert resp.status_code == 200 and resp.json()["last_gate"] == "Needs"
    # no rule for On hold; other edits are never blocked by the stage
    assert patch(client, 6, stage="On hold").status_code == 200


def test_old_mismatch_is_shown_but_does_not_block_other_edits(client, db_path):
    conn = sqlite3.connect(db_path)
    # Beta comes from the sheet: in Production, no gate dates; Dev User (Lead C) leads it
    conn.execute('UPDATE "Initiative" SET "Stage" = \'Production\', "LeadID" = 3 WHERE "UseCaseID" = 2')
    conn.commit()
    conn.close()
    uc = detail(client, 2)
    assert uc["last_gate"] is None and len(uc["stage_problems"]) == 2
    assert patch(client, 2, enabling_team="DiY").status_code == 200
    assert patch(client, 2, scope_gate_date="2026-03-01").status_code == 422  # the deploy gate is still missing


def test_description_and_cost_estimates_are_fixed_after_submitting(client, idea, as_approver):
    for field, value in (("description", "Changed"), ("one_time_costs", 500000), ("running_cost_range", "over_100k")):
        resp = patch(client, 6, **{field: value})
        assert resp.status_code == 422 and "cannot be changed after the idea was submitted" in resp.json()["detail"]
    # open again while a rejected idea is revised
    rejected = client.post("/api/use-cases/6/decision", json={"decision": "reject", "comment": "Too vague"}).json()
    resp = client.patch("/api/use-cases/6", json={"base_revision": rejected["revision"], "description": "Clearer",
                                                  "one_time_costs": 500000, "resubmit": True})
    assert resp.status_code == 200 and resp.json()["description"] == "Clearer"


def test_stage_cannot_go_below_the_one_given_in_form_1(client, submit, db_path):
    created = submit(name="Started late", stage="MVP", scope_gate_date="2026-02-10")
    process(db_path, created["user_input_id"], 7)
    conn = sqlite3.connect(db_path)  # what the DAG takes over from the create record
    conn.execute('UPDATE "Initiative" SET "Stage" = \'MVP\', "ScopeGateDate" = \'2026-02-10 00:00:00\' WHERE "UseCaseID" = 7')
    conn.commit()
    conn.close()
    uc = detail(client, 7)
    assert uc["stage_floor"] == "MVP"
    resp = patch(client, 7, stage="PoC")
    assert resp.status_code == 422 and "cannot go below MVP" in resp.json()["detail"]
    assert patch(client, 7, stage="Implementation").status_code == 200
    assert patch(client, 7, stage="MVP").status_code == 200  # back to the floor is fine
    assert patch(client, 7, stage="On hold").status_code == 200  # outside the order


def test_new_idea_in_a_later_stage_needs_its_gate_dates(submit, client):
    resp = client.post("/api/initiatives", json=form1(name="Later", stage="MVP"))
    assert resp.status_code == 422 and "scope gate" in resp.json()["detail"]
    created = submit(name="Later", stage="MVP", needs_gate_date="2026-01-10", scope_gate_date="2026-02-10")
    pending = detail(client, created["id"])
    assert (pending["scope_gate_date"], pending["last_gate"]) == ("2026-02-10T00:00:00", "Scope")


def test_approval_keeps_a_needs_date_from_the_past_and_never_ends_after_a_later_gate(client, submit, db_path,
                                                                                     as_approver):
    created = submit(name="Dated", stage="PoC", scope_gate_date="2026-02-10")  # needs gate not dated
    process(db_path, created["user_input_id"], 7)
    conn = sqlite3.connect(db_path)
    conn.execute('UPDATE "Initiative" SET "Stage" = \'PoC\', "ScopeGateDate" = \'2026-02-10 00:00:00\''
                 ' WHERE "UseCaseID" = 7')
    conn.commit()
    conn.close()
    approved = client.post("/api/use-cases/7/decision", json={"decision": "approve", "lead_id": 3}).json()
    assert approved["needs_gate_date"] == "2026-02-10T00:00:00" and approved["stage_problems"] == []


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


DEMO_USERS = (
    '[{"name": "Jonas", "email": "jonas@demo.local", "groups": ["app_50hzt_aap_communities_all__x"]},'
    ' {"name": "Demo Approver", "email": "approver@demo.local", "groups": ["ai_cockpit_admins"]}]'
)
JONAS = {"Authorization": "Bearer dev:jonas@demo.local"}
APPROVER = {"Authorization": "Bearer dev:Approver@demo.local"}


def test_demo_one_user_submits_another_approves(client, db_path, monkeypatch):
    monkeypatch.setenv("EG_AUTH_DEV_USERS", DEMO_USERS)
    assert client.get("/api/auth/rights").json()["user"] == "Jonas"  # no token: the first persona
    created = client.post("/api/initiatives", json=form1(business_unit="ETB"), headers=JONAS)
    assert created.status_code == 201, created.text
    assert client.get("/api/approvals", headers=JONAS).status_code == 403

    process(db_path, created.json()["user_input_id"], 6)
    inbox = client.get("/api/approvals", headers=APPROVER).json()
    assert [(i["id"], i["submitted_by"], i["can_decide"]) for i in inbox] == [(6, "Jonas", True)]
    resp = client.post("/api/use-cases/6/decision", json={"decision": "approve", "lead_id": 3}, headers=APPROVER)
    assert resp.status_code == 200, resp.text
    assert client.get("/api/approvals", headers=APPROVER).json() == []

    mine = client.get("/api/me/use-cases", headers=JONAS).json()
    assert [(u["id"], u["approval_status"], u["todos"]) for u in mine] == [(6, "approved", ["complete_details"])]
    assert client.get("/api/me/use-cases", headers=APPROVER).json() == []  # not the approver's own


def test_demo_presenter_switches_to_approver(client, db_path, monkeypatch):
    monkeypatch.setenv("EG_AUTH_DEV_USERS", DEMO_USERS)
    monkeypatch.setenv("AI_COCKPIT_DEMO_PRESENTERS", "JONAS@demo.local")
    demo = {**JONAS, "X-Demo-Role": "approver"}
    rights = client.get("/api/auth/rights", headers=JONAS).json()
    assert (rights["rights"]["canApprove"], rights["demo_presenter"], rights["demo_approver"]) == (False, True, False)
    assert (rights["email"], rights["groups"]) == ("jonas@demo.local", ["app_50hzt_aap_communities_all__x"])

    # as a normal user: submit, no inbox
    created = client.post("/api/initiatives", json=form1(business_unit="ETB"), headers=JONAS)
    assert created.status_code == 201, created.text
    assert client.get("/api/approvals", headers=JONAS).status_code == 403
    process(db_path, created.json()["user_input_id"], 6)

    # switched to demo approver: the idea is in the inbox and can be approved (approver rights only)
    rights = client.get("/api/auth/rights", headers=demo).json()
    assert (rights["user"], rights["rights"]["canApprove"], rights["rights"]["canAdmin"], rights["demo_approver"]) == (
        "Jonas (demo approver)", True, False, True)
    assert [i["id"] for i in client.get("/api/approvals", headers=demo).json()] == [6]
    resp = client.post("/api/use-cases/6/decision", json={"decision": "approve", "lead_id": 3}, headers=demo)
    assert resp.status_code == 200, resp.text
    assert resp.json()["changed_by"] == "Jonas (demo approver)"  # recorded with the marker

    # back as the normal user: approved, linked to Jonas, with the form 2 to-do
    mine = client.get("/api/me/use-cases", headers=JONAS).json()
    assert [(u["id"], u["approval_status"], u["roles"], u["todos"]) for u in mine] == [
        (6, "approved", ["submitter", "owner"], ["complete_details"])]


def test_demo_role_header_is_ignored_for_everyone_else(client, idea, monkeypatch):
    monkeypatch.setenv("EG_AUTH_DEV_USERS", DEMO_USERS)
    sneaky = {"Authorization": "Bearer dev:jonas@demo.local", "X-Demo-Role": "approver"}
    # no presenters configured (the default)
    assert client.get("/api/approvals", headers=sneaky).status_code == 403
    rights = client.get("/api/auth/rights", headers=sneaky).json()
    assert (rights["rights"]["canApprove"], rights["demo_presenter"], rights["demo_approver"]) == (False, False, False)
    # someone else is the presenter
    monkeypatch.setenv("AI_COCKPIT_DEMO_PRESENTERS", "approver@demo.local")
    assert client.get("/api/approvals", headers=sneaky).status_code == 403
    assert client.post("/api/use-cases/6/decision", json={"decision": "approve", "lead_id": 3},
                       headers=sneaky).status_code == 403


def test_demo_presenter_by_sso_name(client, monkeypatch):
    monkeypatch.setenv("EG_AUTH_DEV_USERS", DEMO_USERS)
    monkeypatch.setenv("AI_COCKPIT_DEMO_PRESENTERS", " jonas ")
    rights = client.get("/api/auth/rights", headers={**JONAS, "X-Demo-Role": "approver"}).json()
    assert (rights["demo_presenter"], rights["rights"]["canApprove"]) == (True, True)
    other = client.get("/api/auth/rights", headers={**APPROVER, "X-Demo-Role": "approver"}).json()
    assert other["demo_presenter"] is False


def test_approver_role_from_the_user_table(client, monkeypatch):
    rights = client.get("/api/auth/rights").json()
    assert (rights["role"], rights["user_id"], rights["rights"]["canApprove"]) == ("user", 1, False)
    assert client.get("/api/users").status_code == 403
    # the first approver comes from AI_COCKPIT_APPROVERS (e-mail or SSO name) ...
    monkeypatch.setenv("AI_COCKPIT_APPROVERS", "DEV.USER@example.com")
    rights = client.get("/api/auth/rights").json()
    assert (rights["role"], rights["rights"]["canApprove"], rights["rights"]["canManageUsers"]) == (
        "approver", True, True)
    monkeypatch.delenv("AI_COCKPIT_APPROVERS")
    assert client.get("/api/auth/rights").json()["role"] == "approver"  # stored in AppUser
    assert client.get("/api/approvals").status_code == 200

    # ... who manages the others on the Users page
    monkeypatch.setenv("EG_AUTH_DEV_USERS", DEMO_USERS)
    client.get("/api/auth/rights", headers=JONAS)  # Jonas signs in: a user
    me = {"Authorization": "Bearer dev:dev.user@example.com"}
    monkeypatch.setenv("EG_AUTH_DEV_USERS", DEMO_USERS[:-1] + ', {"name": "Dev User", "email": "dev.user@example.com",'
                       ' "groups": []}]')
    users = {u["email"]: u for u in client.get("/api/users", headers=me).json()}
    assert (users["jonas@demo.local"]["role"], users["dev.user@example.com"]["business_unit"]) == ("user", "ETB")
    resp = client.put(f"/api/users/{users['jonas@demo.local']['id']}/role", json={"role": "approver"}, headers=me)
    assert resp.status_code == 200 and resp.json()["role"] == "approver"
    assert client.get("/api/approvals", headers=JONAS).status_code == 200
    assert client.put(f"/api/users/{users['dev.user@example.com']['id']}/role", json={"role": "user"},
                      headers=me).status_code == 422  # not from oneself
    assert client.put("/api/users/99/role", json={"role": "user"}, headers=me).status_code == 404


def test_a_presenter_who_is_an_approver_can_show_the_normal_view(client, idea, monkeypatch):
    monkeypatch.setenv("EG_AUTH_DEV_USERS", DEMO_USERS)
    monkeypatch.setenv("AI_COCKPIT_APPROVERS", "jonas@demo.local")
    monkeypatch.setenv("AI_COCKPIT_DEMO_PRESENTERS", "jonas@demo.local")
    assert client.get("/api/approvals", headers=JONAS).status_code == 403  # switch on "Normal user"
    switched = {**JONAS, "X-Demo-Role": "approver"}
    rights = client.get("/api/auth/rights", headers=switched).json()
    assert (rights["user"], rights["rights"]["canApprove"]) == ("Jonas", True)  # no marker: a real approver


def test_parallel_first_requests_create_one_user(client, monkeypatch):
    """The UI's first page load sends several requests at once; all of them see the same new user."""
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setenv("EG_AUTH_DEV_USERS", DEMO_USERS)
    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(lambda _: client.get("/api/me/use-cases", headers=JONAS).status_code, range(16)))
    assert set(codes) == {200}
