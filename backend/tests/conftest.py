import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import get_app
from app.models import Base, Initiative, Owner, RiskClassification, SolutionType, ValueType


@pytest.fixture(autouse=True)
def dev_auth(monkeypatch):
    # The eg-auth stub only supports dev mode; tests that need "signed out"
    # switch it off again.
    monkeypatch.setenv("EG_AUTH_DEV_MODE", "true")
    monkeypatch.setenv("EG_AUTH_DEV_GROUPS", '["app_50hzt_aap_communities_all__x"]')


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        etb = Owner(name="Owner A", department="Assets", category="ETB")
        it = Owner(name="Owner B", department="Innovation", category="IT")
        copilot = SolutionType(name="Copilot", description="MS Copilot")
        capex = ValueType(name="CAPEX delivery", description="On time")
        low = RiskClassification(id=1, name="Sehr geringes Risiko", description="d1", derived_action="a1")
        medium = RiskClassification(id=2, name="Geringes Risiko", description="d2", derived_action="a2")
        unused = RiskClassification(id=5, name="Sehr hohes Risiko", description="d5", derived_action="a5")
        s.add_all([etb, it, copilot, capex, low, medium, unused])
        s.flush()
        now = datetime.datetime(2026, 10, 23)
        s.add_all(
            [
                # potential = (10k+20k+30k+40k) x 0.6 x 0.9 = 54,000; cost = 75k/3 + 19k = 44,000
                Initiative(name="Alpha", description="100% automation", stage="Idea",
                           efficiency_score_eur=10000.0, quality_score_eur=20000.0,
                           risk_reduction_score_eur=30000.0, strategic_value_score_eur=40000.0,
                           confidence_score=0.6, delivery_score=0.9, solution_complexity_score=3.0,
                           one_time_costs=75000.0, operating_costs=19000.0, depreciation_years=3,
                           owner=etb, solution_type=copilot, value_type=capex, risk_classification=medium,
                           date_start=datetime.datetime(2026, 1, 1), timestamp=now),
                # potential = 4 x 5k x 0.35 x 0.65 = 4,550; cost = 30k/3 + 7.5k = 17,500
                Initiative(name="Beta", description="under_score", stage="PoC",
                           efficiency_score_eur=5000.0, quality_score_eur=5000.0,
                           risk_reduction_score_eur=5000.0, strategic_value_score_eur=5000.0,
                           confidence_score=0.35, delivery_score=0.65,
                           one_time_costs=30000.0, operating_costs=7500.0, depreciation_years=3,
                           owner=etb, risk_classification=low, timestamp=now),
                Initiative(name="Gamma", stage="Idea", owner=it, risk_classification=low, timestamp=now),
                Initiative(name="Delta", stage="Unknown", owner=None, risk_classification=low, timestamp=now),
            ]
        )
        s.commit()
    engine.dispose()
    return path


@pytest.fixture()
def client(db_path):
    return TestClient(get_app(db_path))
