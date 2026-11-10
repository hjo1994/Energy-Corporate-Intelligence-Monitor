import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import get_app
from app.models import (
    AppUser,
    AssessedInitiative,
    Base,
    BusinessTransaction,
    Initiative,
    Owner,
    RiskClassification,
    SolutionType,
    ValueType,
)

APPROVERS = "ai_cockpit_approvers"
ADMINS = "ai_cockpit_admins"
NOW = datetime.datetime(2026, 10, 23)
ANSWERS = dict(employee_personal_data="no", performance_or_behaviour_control=False, decisions_on_employees="none",
               profiling_of_individuals=False, changes_employee_workflows=False, prohibited_practice=False)


@pytest.fixture(autouse=True)
def dev_auth(monkeypatch):
    # The eg-auth stub only supports dev mode; tests that need "signed out"
    # switch it off again. The stub's user is "Dev User" (dev.user@example.com).
    monkeypatch.setenv("EG_AUTH_DEV_MODE", "true")
    monkeypatch.setenv("EG_AUTH_DEV_GROUPS", '["app_50hzt_aap_communities_all__x"]')
    monkeypatch.setenv("AI_COCKPIT_APPROVER_GROUPS", APPROVERS)
    monkeypatch.setenv("AI_COCKPIT_ADMIN_GROUPS", ADMINS)
    monkeypatch.setenv("AI_COCKPIT_DEMO_ALL_APPROVERS", "false")  # the tests check the real rights


@pytest.fixture()
def as_approver(monkeypatch):
    monkeypatch.setenv("EG_AUTH_DEV_GROUPS", f'["app_50hzt_aap_communities_all__x", "{APPROVERS}"]')


def version(use_case_id, name, bt, **over):
    """A silver version (sheet use case unless overridden)."""
    return Initiative(use_case_id=use_case_id, name=name, key_hash=f"key-{name.lower()}", row_hash=f"row-{name}",
                      business_transaction=bt, timestamp=NOW, **{"is_active": True, **ANSWERS, **over})


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        # the stub's "Dev User" has signed in before and is the owner "Lead C"
        s.add(AppUser(id=1, name="Dev User", email="dev.user@example.com", role="user"))
        s.flush()
        etb = Owner(id=1, name="Owner A", department="Assets", category="ETB")
        it = Owner(id=2, name="Owner B", department="Innovation", category="IT")
        me = Owner(id=3, name="Lead C", department="Assets", category="ETB", user_id=1, source="app")
        copilot = SolutionType(id=1, name="Copilot", description="MS Copilot")
        capex = ValueType(id=1, name="CAPEX delivery", description="On time")
        low = RiskClassification(id=1, name="Sehr geringes Risiko", description="d1", derived_action="a1")
        medium = RiskClassification(id=2, name="Geringes Risiko", description="d2", derived_action="a2")
        unused = RiskClassification(id=5, name="Sehr hohes Risiko", description="d5", derived_action="a5")
        s.add_all([etb, it, me, copilot, capex, low, medium, unused])
        s.flush()
        bt = BusinessTransaction(id=1, bronze_id=1, bronze_table_name="ETB_Initiatives_Extract")
        s.add(bt)
        s.flush()
        alpha = dict(description="100% automation", stage="Ideation",
                     efficiency_score_eur=10000.0, quality_score_eur=20000.0, risk_reduction_score_eur=30000.0,
                     strategic_value_score_eur=40000.0, confidence_score=0.6, delivery_score=0.9,
                     solution_complexity_score=3.0, one_time_costs=75000.0, running_costs=19000.0,
                     depreciation_years=3, owner=etb, solution_type=copilot, value_type=capex,
                     date_start=datetime.datetime(2026, 1, 1), changes_employee_workflows=True)
        versions = [
            # Alpha has two versions; the second is current: potential = 100k x 0.6 x 0.9 = 54,000,
            # cost = 75k/3 + 19k = 44,000
            version(1, "Alpha", bt, **{**alpha, "stage": "Ideation"}),
            version(1, "Alpha", bt, **alpha),
            # potential = 4 x 5k x 0.35 x 0.65 = 4,550; cost = 30k/3 + 7.5k = 17,500
            version(2, "Beta", bt, description="under_score", stage="PoC",
                    efficiency_score_eur=5000.0, quality_score_eur=5000.0, risk_reduction_score_eur=5000.0,
                    strategic_value_score_eur=5000.0, confidence_score=0.35, delivery_score=0.65,
                    one_time_costs=30000.0, running_costs=7500.0, depreciation_years=3, owner=etb),
            version(3, "Gamma", bt, stage="Ideation", owner=it),  # incomplete: not in gold
            version(4, "Delta", bt, stage="Unknown", owner=None),  # incomplete: not in gold
            # no longer in its source sheet: soft-deleted, hidden by default
            version(5, "Omega", bt, stage="Ideation", owner=etb, is_active=False,
                    efficiency_score_eur=1.0, quality_score_eur=0.0, risk_reduction_score_eur=0.0,
                    strategic_value_score_eur=0.0, confidence_score=1.0, delivery_score=1.0,
                    one_time_costs=0.0, running_costs=0.0, depreciation_years=5),
        ]
        s.add_all(versions)
        s.flush()
        s.add_all([
            AssessedInitiative(use_case_id=1, initiative_id=versions[1].id, potential_value=54000.0,
                               realized_value=None, risk_classification_id=2, assessed_at=NOW),
            AssessedInitiative(use_case_id=2, initiative_id=versions[2].id, potential_value=4550.0,
                               realized_value=1000.0, risk_classification_id=1, assessed_at=NOW),
            AssessedInitiative(use_case_id=5, initiative_id=versions[5].id, potential_value=1.0,
                               realized_value=None, risk_classification_id=1, assessed_at=NOW),
        ])
        s.commit()
    engine.dispose()
    return path


@pytest.fixture()
def client(db_path):
    return TestClient(get_app(db_path))
