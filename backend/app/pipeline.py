"""Triggers the input orchestration after a user action was written to bronze.

The DAGs are event-driven (Airflow Datasets): bronze_to_silver_user_input runs
when the Dataset of UserActionExtracts gets an event. The sheets get theirs from
raw_to_bronze; the UI's actions are written by the Backend itself, so after each
commit it posts the event to the Airflow REST API (POST /api/v1/datasets/events,
Airflow >= 2.9, basic auth of a technical user with role Op).

Fire and forget in a thread: the request does not wait for Airflow. Without
AI_COCKPIT_AIRFLOW_URL nothing is sent (local runs, tests). A failed call is
logged; the action stays in bronze and the next event (or a manual trigger of
bronze_to_silver_user_input) processes it with everything else not yet done.
"""
from __future__ import annotations

import base64
import json
import logging
import threading
import urllib.request

from app.config import airflow_api

log = logging.getLogger(__name__)

USER_ACTION_DATASET = "ai-cockpit://bronze/UserActionExtracts"  # SourceConfig.asset_uri of the pipeline
TIMEOUT_SECONDS = 10


def notify_user_action() -> None:
    """Post the Dataset event in the background (no-op without AI_COCKPIT_AIRFLOW_URL)."""
    api = airflow_api()
    if api is None:
        return
    threading.Thread(target=post_dataset_event, args=(api,), name="airflow-dataset-event", daemon=True).start()


def post_dataset_event(api) -> bool:
    url, user, password = api
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/v1/datasets/events",
        data=json.dumps({"dataset_uri": USER_ACTION_DATASET, "extra": {"from": "ai-cockpit-backend"}}).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    if user:
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            log.info("Dataset event %s sent to Airflow (%s)", USER_ACTION_DATASET, response.status)
            return True
    except Exception as err:  # noqa: BLE001 — never let Airflow break a saved action
        log.warning("Could not send the Dataset event to Airflow (%s); the action waits in bronze", err)
        return False
