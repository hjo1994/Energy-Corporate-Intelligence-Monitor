import os
import sqlite3

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
        "/api/business-units", "/api/statuses", "/api/solution-types", "/api/value-types",
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
    delta = next(i for i in body["items"] if i["name"] == "Delta")
    assert delta["owner"] is None and delta["solution_type"] is None


def test_filter_status_multi_and_business_unit(client):
    assert sorted(names(client.get("/api/initiatives?status=Idea&status=PoC"))) == ["Alpha", "Beta", "Gamma"]
    resp = client.get("/api/initiatives?business_unit=ETB")
    assert sorted(names(resp)) == ["Alpha", "Beta"]
    assert resp.json()["total"] == 2


def test_search_escapes_like_wildcards(client):
    assert names(client.get("/api/initiatives?search=100%25")) == ["Alpha"]
    assert names(client.get("/api/initiatives?search=under_score")) == ["Beta"]
    assert names(client.get("/api/initiatives?search=zzz")) == []


def test_sort_puts_nulls_last_in_both_directions(client):
    asc = names(client.get("/api/initiatives?sort=value_score&order=asc"))
    desc = names(client.get("/api/initiatives?sort=value_score&order=desc"))
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
    assert s["with_value_score"] == 2 and s["without_value_score"] == 2
    assert s["average_value_score"] == 6.5
    assert s["without_owner"] == 1
    assert {x["status"]: x["count"] for x in s["by_status"]} == {"Idea": 2, "PoC": 1, "Unknown": 1}


def test_reference_endpoints(client):
    assert [o["name"] for o in client.get("/api/owners").json()] == ["Owner A", "Owner B"]
    assert [o["name"] for o in client.get("/api/owners?business_unit=IT").json()] == ["Owner B"]
    assert client.get("/api/solution-types").json()[0]["name"] == "Copilot"
    assert client.get("/api/value-types").json()[0]["name"] == "CAPEX delivery"
    bu = {b["name"]: b["count"] for b in client.get("/api/business-units").json()}
    assert bu == {"ETB": 2, "IT": 1}  # Delta has no owner -> in no business unit
    assert {s["status"]: s["count"] for s in client.get("/api/statuses").json()}["Idea"] == 2


def test_database_is_opened_read_only(client, db_path):
    # The API has no write path, but the SQLite handle itself must refuse writes too.
    from app.db import make_engine
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    import pytest

    with make_engine(db_path).connect() as conn:
        with pytest.raises(OperationalError):
            conn.execute(text("DELETE FROM initiative"))


def test_sees_file_replaced_by_atomic_rename(db_path, tmp_path):
    # Writer swaps the file via rename; a pooled connection would keep reading the old inode.
    client = TestClient(get_app(db_path))
    assert client.get("/api/initiatives").json()["total"] == 4

    new = tmp_path / "new.db"
    conn = sqlite3.connect(new)
    conn.executescript(
        "CREATE TABLE owner(id INTEGER PRIMARY KEY, category TEXT, name TEXT NOT NULL, department TEXT);"
        "CREATE TABLE solution_type(id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT);"
        "CREATE TABLE value_type(id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT);"
        "CREATE TABLE initiative(id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, status TEXT NOT NULL,"
        " date_start DATETIME, date_delivery DATETIME, value_score FLOAT, solution_complexity_score FLOAT,"
        " owner_id INTEGER, value_type_id INTEGER, solution_type_id INTEGER);"
        "INSERT INTO initiative(id, name, status) VALUES (1, 'Only', 'Idea');"
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
    for sort in ["value_score", "solution_complexity_score", "date_delivery", "name", "status"]:
        for order in ["asc", "desc"]:
            assert client.get(f"/api/initiatives?sort={sort}&order={order}").status_code == 200
    assert statements and not any("NULLS" in s.upper() for s in statements)
