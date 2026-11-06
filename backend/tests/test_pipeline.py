"""After every user action the Backend posts a Dataset event to Airflow (app/pipeline.py)."""
import base64
import json

import pytest

from app import pipeline
from tests.test_user_input import form1


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_dataset_event_request(monkeypatch):
    sent = []
    monkeypatch.setattr(pipeline.urllib.request, "urlopen", lambda request, timeout: sent.append(request) or _Response())
    assert pipeline.post_dataset_event(("http://airflow:8080/", "svc", "secret")) is True
    (request,) = sent
    assert (request.full_url, request.get_method()) == ("http://airflow:8080/api/v1/datasets/events", "POST")
    assert json.loads(request.data)["dataset_uri"] == "ai-cockpit://bronze/UserActionExtracts"
    assert request.get_header("Authorization") == "Basic " + base64.b64encode(b"svc:secret").decode()


def test_unreachable_airflow_is_only_logged(monkeypatch, caplog):
    def fail(request, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(pipeline.urllib.request, "urlopen", fail)
    assert pipeline.post_dataset_event(("http://airflow:8080", "", "")) is False
    assert "waits in bronze" in caplog.text


def test_nothing_is_sent_without_an_airflow_url(monkeypatch):
    monkeypatch.delenv("AI_COCKPIT_AIRFLOW_URL", raising=False)
    monkeypatch.setattr(pipeline, "post_dataset_event", lambda api: pytest.fail("no Airflow configured"))
    pipeline.notify_user_action()


@pytest.fixture()
def events(monkeypatch):
    calls = []
    monkeypatch.setattr("app.api.initiatives.notify_user_action", lambda: calls.append(1))
    return calls


def test_every_user_action_triggers_the_pipeline(client, events):
    assert client.post("/api/initiatives", json=form1()).status_code == 201
    assert events == [1]
    assert client.post("/api/initiatives", json={**form1(), "name": ""}).status_code == 422
    assert events == [1]  # nothing stored, nothing sent


def test_the_event_is_sent_in_the_background(monkeypatch):
    monkeypatch.setenv("AI_COCKPIT_AIRFLOW_URL", "http://airflow:8080")
    monkeypatch.setenv("AI_COCKPIT_AIRFLOW_USER", "svc")
    monkeypatch.setenv("AI_COCKPIT_AIRFLOW_PASSWORD", "secret")
    sent = []
    monkeypatch.setattr(pipeline, "post_dataset_event", sent.append)
    pipeline.notify_user_action()
    for thread in __import__("threading").enumerate():
        if thread.name == "airflow-dataset-event":
            thread.join(5)
    assert sent == [("http://airflow:8080", "svc", "secret")]
