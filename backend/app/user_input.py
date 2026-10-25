"""Input form support: duplicate key, provisional (pending) values and the
DAG trigger.

The binding values are computed by the input orchestration's
bronze_to_silver_user_input DAG (transforms/user_input_heuristic.py). Until
it has run, a submitted initiative is shown as "pending" with the same
formulas computed here — kept identical by the shared test cases in
tests/fixtures/user_input_cases.json (copy of the input-orchestration file):

- Efficiency     = CasesPerYear x HoursSavedPerCase x HOURLY_RATE_EUR
- Quality        = CasesPerYear x ErrorRateBefore x ErrorsAvoided x CostPerError
- Risk reduction = RiskEventsPerYear x EventsAvoided x CostPerEvent
- Strategic      = DelayEventsPerYear x CostOfDelayPerEvent x LeadTimeSaved
  (an incomplete lever counts as zero)
- confidence from EstimateBasis, delivery from DeliveryLikelihood; costs are
  expected costs (entered costs x delivery), written off over 5 years
- risk level: prohibited practice 5; automated decisions or profiling 4;
  personal data, performance/behaviour control or prepared decisions 3;
  pseudonymised data or changed workflows 2; otherwise 1
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import json
import logging
import os
import re
import urllib.request

from app.models import UserInputRecord

logger = logging.getLogger(__name__)

HOURLY_RATE_EUR = 60
DEPRECIATION_YEARS = 5
CONFIDENCE_SCORE = {"rough": 0.35, "benchmark": 0.60, "measured": 0.80}
DELIVERY_SCORE = {"low": 0.40, "medium": 0.65, "high": 0.90}
USER_INPUT_DAG_ID = "bronze_to_silver_user_input"

# ---------- key (same as the input orchestration's transforms/upsert_keys.py) ----------

_SEPARATOR = "\x1f"
_INVISIBLE_CHARS = ("﻿", "​", "‌", "‍")


def _normalize(value: str | None) -> str:
    text = " ".join(str(value or "").replace("\xa0", " ").split())
    for ch in _INVISIBLE_CHARS:
        text = text.replace(ch, "")
    return text


def key_hash(business_unit: str, name: str | None) -> str:
    """Identity of an initiative: business unit + normalized, casefolded name."""
    return hashlib.sha256(_SEPARATOR.join([business_unit, _normalize(name).casefold()]).encode("utf-8")).hexdigest()


# ---------- provisional values ----------


def _product(*values: float | None, factor: float = 1.0) -> float:
    if any(v is None for v in values):
        return 0.0
    result = factor
    for v in values:
        result *= v
    return result


def provisional_values(r: UserInputRecord) -> dict:
    """The silver value/cost columns as the DAG will compute them."""
    delivery = DELIVERY_SCORE[r.delivery_likelihood]
    return {
        "efficiency_score_eur": _product(r.cases_per_year, r.hours_saved_per_case, factor=HOURLY_RATE_EUR),
        "quality_score_eur": _product(r.cases_per_year, r.error_rate_before, r.errors_avoided, r.cost_per_error),
        "risk_reduction_score_eur": _product(r.risk_events_per_year, r.events_avoided, r.cost_per_event),
        "strategic_value_score_eur": _product(r.delay_events_per_year, r.cost_of_delay_per_event, r.lead_time_saved),
        "confidence_score": CONFIDENCE_SCORE[r.estimate_basis],
        "delivery_score": delivery,
        "one_time_costs": r.one_time_costs * delivery,
        "operating_costs": r.operating_costs * delivery,
        "depreciation_years": DEPRECIATION_YEARS,
    }


def risk_level(r: UserInputRecord) -> int:
    if r.prohibited_practice:
        return 5
    if r.decisions_on_employees == "automated" or r.profiling_of_individuals:
        return 4
    if r.employee_personal_data == "yes" or r.performance_or_behaviour_control or r.decisions_on_employees == "prepares":
        return 3
    if r.employee_personal_data == "pseudonymised" or r.changes_employee_workflows:
        return 2
    return 1


_QUARTER = re.compile(r"^Q([1-4]) (\d{4})$")


def quarter_start(label: str | None) -> datetime.datetime | None:
    match = _QUARTER.match(label or "")
    return datetime.datetime(int(match.group(2)), (int(match.group(1)) - 1) * 3 + 1, 1) if match else None


# ---------- DAG trigger ----------


def trigger_user_input_dag() -> None:
    """Start a bronze_to_silver_user_input run via the Airflow REST API.

    Best effort: AIRFLOW_API_URL (e.g. http://airflow-webserver:8080),
    AIRFLOW_API_USER and AIRFLOW_API_PASSWORD come from the environment. If they
    are missing or the call fails, the input stays stored and is picked up by
    the next run; it is only logged.
    """
    base_url = os.environ.get("AIRFLOW_API_URL", "").rstrip("/")
    user = os.environ.get("AIRFLOW_API_USER", "")
    password = os.environ.get("AIRFLOW_API_PASSWORD", "")
    if not base_url:
        logger.info("AIRFLOW_API_URL not set — %s not triggered, the input waits for the next run", USER_INPUT_DAG_ID)
        return
    request = urllib.request.Request(
        f"{base_url}/api/v1/dags/{USER_INPUT_DAG_ID}/dagRuns",
        data=json.dumps({"conf": {}}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if user:
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            logger.info("Triggered %s: HTTP %s", USER_INPUT_DAG_ID, response.status)
    except Exception as err:  # noqa: BLE001 — never fail the submission because of Airflow
        logger.warning("Could not trigger %s (%s) — the input waits for the next run", USER_INPUT_DAG_ID, err)
