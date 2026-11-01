"""Formulas and helpers for user actions (bronze UserActionExtracts).

The Backend does not trigger Airflow: the sensor of bronze_to_silver_user_input
checks the table every minute and applies new actions to silver; silver_to_gold
then assesses the use case. Until that has happened, the API shows the action's
effect with the same formulas computed here — kept identical to the input
orchestration (transforms/user_input_heuristic.py, transforms/gold.py) by the
shared test cases in tests/fixtures/user_input_cases.json:

- Efficiency     = CasesPerYear x HoursSavedPerCase x HOURLY_RATE_EUR
- Quality        = CasesPerYear x ErrorRateBefore x ErrorsAvoided x CostPerError
- Risk reduction = RiskEventsPerYear x EventsAvoided x CostPerEvent
- Strategic      = DelayEventsPerYear x CostOfDelayPerEvent x LeadTimeSaved
  (an incomplete lever counts as zero)
- confidence from EstimateBasis, delivery from DeliveryLikelihood; costs are
  expected costs (entered costs x delivery), written off over 5 years
- potential = sum of the buckets x confidence x delivery
- risk level: prohibited practice 5; automated decisions or profiling 4;
  personal data, performance/behaviour control or prepared decisions 3;
  pseudonymised data or changed workflows 2; otherwise 1

Drivers are merged over all actions of a use case in order (a later value
wins), exactly like the DAG does, so an update only carries what changed.
"""
from __future__ import annotations

import datetime
import hashlib
import re
from collections.abc import Iterable

HOURLY_RATE_EUR = 60
DEPRECIATION_YEARS = 5
CONFIDENCE_SCORE = {"rough": 0.35, "benchmark": 0.60, "measured": 0.80}
DELIVERY_SCORE = {"low": 0.40, "medium": 0.65, "high": 0.90}

# Running costs are asked as a range in form 1; the bronze record stores the
# range's representative value (EUR per year), the API maps it back.
RUNNING_COST_RANGES = {
    "up_to_10k": ("up to 10k € / year", 5_000.0),
    "10k_to_50k": ("10k–50k € / year", 30_000.0),
    "50k_to_100k": ("50k–100k € / year", 75_000.0),
    "over_100k": ("more than 100k € / year", 150_000.0),
}


def running_cost_range(value: float | None) -> str | None:
    """The range an (expected or entered) yearly amount falls in."""
    if value is None:
        return None
    if value <= 10_000:
        return "up_to_10k"
    if value <= 50_000:
        return "10k_to_50k"
    if value <= 100_000:
        return "50k_to_100k"
    return "over_100k"


DRIVERS = (
    "cases_per_year", "hours_saved_per_case",
    "error_rate_before", "errors_avoided", "cost_per_error",
    "risk_events_per_year", "events_avoided", "cost_per_event",
    "delay_events_per_year", "cost_of_delay_per_event", "lead_time_saved",
)
BASE_INPUTS = ("estimate_basis", "delivery_likelihood", "one_time_costs", "operating_costs")
VALUE_INPUTS = (*DRIVERS, *BASE_INPUTS)

# ---------- key (same as the input orchestration's transforms/upsert_keys.py) ----------

_SEPARATOR = "\x1f"
_INVISIBLE_CHARS = ("﻿", "​", "‌", "‍")


def _normalize(value: str | None) -> str:
    text = " ".join(str(value or "").replace("\xa0", " ").split())
    for ch in _INVISIBLE_CHARS:
        text = text.replace(ch, "")
    return text


def key_hash(business_unit: str, name: str | None) -> str:
    """Identity of a use case: business unit + normalized, casefolded name."""
    return hashlib.sha256(_SEPARATOR.join([business_unit, _normalize(name).casefold()]).encode("utf-8")).hexdigest()


def same_name(a: str | None, b: str | None) -> bool:
    return _normalize(a).casefold() == _normalize(b).casefold()


# ---------- merging and provisional values ----------


def merged(actions: Iterable[object], fields: Iterable[str] = VALUE_INPUTS) -> dict:
    """The actions' values in order, a later non-empty value wins."""
    fields = tuple(fields)
    result: dict = {}
    for action in actions:
        for name in fields:
            value = getattr(action, name, None)
            if value is not None:
                result[name] = value
    return result


def _product(*values: float | None, factor: float = 1.0) -> float:
    if any(v is None for v in values):
        return 0.0
    result = factor
    for v in values:
        result *= v
    return result


def provisional_values(inputs: dict) -> dict | None:
    """The silver value/cost columns as the DAG will compute them from merged
    inputs; None while the base inputs are incomplete."""
    if any(inputs.get(c) is None for c in BASE_INPUTS):
        return None
    g = inputs.get
    delivery = DELIVERY_SCORE[g("delivery_likelihood")]
    return {
        "efficiency_score_eur": _product(g("cases_per_year"), g("hours_saved_per_case"), factor=HOURLY_RATE_EUR),
        "quality_score_eur": _product(g("cases_per_year"), g("error_rate_before"), g("errors_avoided"),
                                      g("cost_per_error")),
        "risk_reduction_score_eur": _product(g("risk_events_per_year"), g("events_avoided"), g("cost_per_event")),
        "strategic_value_score_eur": _product(g("delay_events_per_year"), g("cost_of_delay_per_event"),
                                              g("lead_time_saved")),
        "confidence_score": CONFIDENCE_SCORE[g("estimate_basis")],
        "delivery_score": delivery,
        "one_time_costs": g("one_time_costs") * delivery,
        "running_costs": g("operating_costs") * delivery,
        "depreciation_years": DEPRECIATION_YEARS,
    }


def risk_level(answers: object) -> int | None:
    """Risk level from the six answers (attributes or dict keys); None if one is missing."""
    get = answers.get if isinstance(answers, dict) else lambda k: getattr(answers, k, None)
    values = [get(k) for k in ("employee_personal_data", "performance_or_behaviour_control",
                               "decisions_on_employees", "profiling_of_individuals",
                               "changes_employee_workflows", "prohibited_practice")]
    if any(v is None for v in values):
        return None
    personal, control, decisions, profiling, workflows, prohibited = values
    if prohibited:
        return 5
    if decisions == "automated" or profiling:
        return 4
    if personal == "yes" or control or decisions == "prepares":
        return 3
    if personal == "pseudonymised" or workflows:
        return 2
    return 1


_QUARTER = re.compile(r"^Q([1-4]) (\d{4})$")


def quarter_start(label: str | None) -> datetime.datetime | None:
    match = _QUARTER.match(label or "")
    return datetime.datetime(int(match.group(2)), (int(match.group(1)) - 1) * 3 + 1, 1) if match else None


def quarter_label(moment: datetime.datetime | None) -> str | None:
    """2027-04-01 -> 'Q2 2027' (the form works with quarters)."""
    return None if moment is None else f"Q{(moment.month - 1) // 3 + 1} {moment.year}"


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
