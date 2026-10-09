import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.main import get_app
from app.models import Base, Initiative, Owner, SolutionType, ValueType


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
        s.add_all([etb, it, copilot, capex])
        s.flush()
        s.add_all(
            [
                Initiative(name="Alpha", description="100% automation", status="Idea",
                           value_score=8.0, solution_complexity_score=3.0,
                           owner=etb, solution_type=copilot, value_type=capex,
                           date_start=datetime.datetime(2026, 1, 1)),
                Initiative(name="Beta", description="under_score", status="PoC",
                           value_score=5.0, owner=etb),
                Initiative(name="Gamma", status="Idea", value_score=None, owner=it),
                Initiative(name="Delta", status="Unknown", owner=None),
            ]
        )
        s.commit()
    engine.dispose()
    return path


@pytest.fixture()
def client(db_path):
    return TestClient(get_app(db_path))
