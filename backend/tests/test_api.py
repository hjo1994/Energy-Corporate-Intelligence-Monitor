import os
import sqlite3

import pytest

from fastapi.testclient import TestClient

from app.main import get_app


def names(resp):
    return [i["name"] for i in resp.json()["items"]]


def test_healthz_is_open_and_independent_of_the_database(tmp_path, monkeypatch):
    monkeypatch.setenv("EG_AUTH_DEV_MODE", "false")
    client = TestClient(get_app(tmp_path / "missing.db"))
    assert client.get("/api/healthz").json() == "OK"


def test_every_data_endpoint_requires_authentication(client, monkeypatch):
    monkeypatch.setenv("EG_AUTH_DEV_MODE", "false")
    for path in [
        "/api/initiatives", "/api/initiatives/1", "/api/initiatives/summary", "/api/owners",
        "/api/business-units", "/api/stages", "/api/risk-classifications", "/api/solution-types",
        "/api/value-types",
        "/api/auth/rights",
    ]:
        assert client.get(path).status_code == 401, path


def test_auth_rights_follow_the_groups(client, monkeypatch):
    body = client.get("/api/auth/rights").json()
    assert body["rights"] == {"canViewInitiatives": True}
    monkeypatch.setenv("EG_AUTH_DEV_GROUPS", '["some_other_group"]')
    assert client.get("/api/auth/rights").json()["rights"] == {"canViewInitiatives": False}
    # reading still works: the API only requires a signed-in user, not the right
    assert client.get("/api/initiatives").status_code == 200


def test_list_nests_owner_and_types(client):
    body = client.get("/api/initiatives").json()
    assert body["total"] == 4
    alpha = next(i for i in body["items"] if i["name"] == "Alpha")
    assert alpha["owner"] == {"id": 1, "name": "Owner A", "department": "Assets", "category": "ETB"}
    assert alpha["solution_type"]["name"] == "Copilot"
    assert alpha["value_type"]["name"] == "CAPEX delivery"
    assert alpha["risk_classification"] == {"id": 2, "name": "Geringes Risiko"}
    delta = next(i for i in body["items"] if i["name"] == "Delta")
    assert delta["owner"] is None and delta["solution_type"] is None


def test_derived_values(client):
    items = {i["name"]: i for i in client.get("/api/initiatives").json()["items"]}
    alpha = items["Alpha"]
    assert alpha["hypothetical_value_eur"] == 100000.0
    assert alpha["potential_value_eur"] == pytest.approx(54000.0)
    assert alpha["annual_cost_eur"] == pytest.approx(44000.0)
    assert alpha["efficiency_score_eur"] == 10000.0 and alpha["confidence_score"] == 0.6
    # missing inputs give null, not 0
    gamma = items["Gamma"]
    assert gamma["hypothetical_value_eur"] is None and gamma["potential_value_eur"] is None
    assert gamma["annual_cost_eur"] is None


def test_filter_stage_multi_and_business_unit(client):
    assert sorted(names(client.get("/api/initiatives?stage=Idea&stage=PoC"))) == ["Alpha", "Beta", "Gamma"]
    resp = client.get("/api/initiatives?business_unit=ETB")
    assert sorted(names(resp)) == ["Alpha", "Beta"]
    assert resp.json()["total"] == 2


def test_filter_risk_classification(client):
    assert names(client.get("/api/initiatives?risk_classification_id=2")) == ["Alpha"]
    assert len(names(client.get("/api/initiatives?risk_classification_id=1&risk_classification_id=2"))) == 4


def test_search_escapes_like_wildcards(client):
    assert names(client.get("/api/initiatives?search=100%25")) == ["Alpha"]
    assert names(client.get("/api/initiatives?search=under_score")) == ["Beta"]
    assert names(client.get("/api/initiatives?search=zzz")) == []


def test_sort_puts_nulls_last_in_both_directions(client):
    asc = names(client.get("/api/initiatives?sort=potential_value_eur&order=asc"))
    desc = names(client.get("/api/initiatives?sort=potential_value_eur&order=desc"))
    assert asc[:2] == ["Beta", "Alpha"] and desc[:2] == ["Alpha", "Beta"]
    assert set(asc[2:]) == set(desc[2:]) == {"Gamma", "Delta"}


def test_pagination_keeps_total(client):
    body = client.get("/api/initiatives?limit=2&offset=1&sort=name").json()
    assert [i["name"] for i in body["items"]] == ["Beta", "Delta"]
    assert body["total"] == 4


def test_invalid_params_rejected(client):
    assert client.get("/api/initiatives?sort=owner").status_code == 422
    assert client.get("/api/initiatives?limit=0").status_code == 422


def test_get_one_and_404(client):
    assert client.get("/api/initiatives/1").json()["name"] == "Alpha"
    assert client.get("/api/initiatives/999").status_code == 404


def test_summary(client):
    s = client.get("/api/initiatives/summary").json()
    assert s["total"] == 4
    assert s["with_potential_value"] == 2 and s["without_potential_value"] == 2
    assert s["total_potential_value_eur"] == pytest.approx(58550.0)
    assert s["average_potential_value_eur"] == pytest.approx(29275.0)
    assert s["total_hypothetical_value_eur"] == pytest.approx(120000.0)
    assert s["total_annual_cost_eur"] == pytest.approx(61500.0)
    assert s["without_owner"] == 1
    assert {x["stage"]: x["count"] for x in s["by_stage"]} == {"Idea": 2, "PoC": 1, "Unknown": 1}
    assert [(r["id"], r["count"]) for r in s["by_risk_classification"]] == [(1, 3), (2, 1)]


def test_reference_endpoints(client):
    assert [o["name"] for o in client.get("/api/owners").json()] == ["Owner A", "Owner B"]
    assert [o["name"] for o in client.get("/api/owners?business_unit=IT").json()] == ["Owner B"]
    assert client.get("/api/solution-types").json()[0]["name"] == "Copilot"
    assert client.get("/api/value-types").json()[0]["name"] == "CAPEX delivery"
    bu = {b["name"]: b["count"] for b in client.get("/api/business-units").json()}
    assert bu == {"ETB": 2, "IT": 1}  # Delta has no owner -> in no business unit
    assert {s["stage"]: s["count"] for s in client.get("/api/stages").json()}["Idea"] == 2
    risks = client.get("/api/risk-classifications").json()
    assert [r["id"] for r in risks] == [1, 2, 5]  # unused levels are listed too
    assert risks[0]["derived_action"] == "a1"


def test_database_is_opened_read_only(client, db_path):
    # The API has no write path, but the SQLite handle itself must refuse writes too.
    from app.db import make_engine
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    import pytest

    with make_engine(db_path).connect() as conn:
        with pytest.raises(OperationalError):
            conn.execute(text("DELETE FROM initiative"))


def test_sees_rows_committed_by_the_writer(db_path):
    # The DAGs write into the same file in short transactions; every request opens the file anew.
    client = TestClient(get_app(db_path))
    assert client.get("/api/initiatives").json()["total"] == 4

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO initiative(name, stage, risk_classification_id, timestamp)"
        " VALUES ('Epsilon', 'Idea', 1, '2026-10-23 00:00:00')"
    )
    conn.commit()
    conn.close()

    assert client.get("/api/initiatives").json()["total"] == 5


def test_sees_file_replaced_by_rename(db_path, tmp_path):
    # E.g. a restored backup: a pooled connection would keep reading the old inode.
    from sqlalchemy import create_engine

    from app.models import Base

    client = TestClient(get_app(db_path))
    assert client.get("/api/initiatives").json()["total"] == 4

    new = tmp_path / "new.db"
    engine = create_engine(f"sqlite:///{new}")
    Base.metadata.create_all(engine)
    engine.dispose()
    conn = sqlite3.connect(new)
    conn.execute(
        "INSERT INTO initiative(id, name, stage, risk_classification_id, timestamp)"
        " VALUES (1, 'Only', 'Idea', 1, '2026-10-23 00:00:00')"
    )
    conn.commit()
    conn.close()
    os.replace(new, db_path)

    assert client.get("/api/initiatives").json()["total"] == 1


def test_missing_database_gives_503(tmp_path):
    client = TestClient(get_app(tmp_path / "missing.db"))
    resp = client.get("/api/initiatives")
    assert resp.status_code == 503 and resp.headers["retry-after"] == "2"


def test_start_command_of_the_platform_works(db_path, monkeypatch):
    # The platform starts the app with `uvicorn app.main:get_app --factory`, i.e. without arguments.
    from app.main import get_app

    monkeypatch.setenv("AI_COCKPIT_DB_PATH", str(db_path))
    assert TestClient(get_app()).get("/api/initiatives/summary").json()["total"] == 4


def test_sql_stays_portable_to_the_cluster_database(client):
    # SQLite 3.26 (cluster image) and MySQL reject NULLS LAST/FIRST.
    from sqlalchemy import event

    statements = []
    event.listen(client.app.state.engine, "before_cursor_execute", lambda c, cur, stmt, *a: statements.append(stmt))
    for sort in ["potential_value_eur", "hypothetical_value_eur", "annual_cost_eur", "solution_complexity_score",
                 "risk_classification", "date_delivery", "name", "stage"]:
        for order in ["asc", "desc"]:
            assert client.get(f"/api/initiatives?sort={sort}&order={order}").status_code == 200
    assert statements and not any("NULLS" in s.upper() for s in statements)
