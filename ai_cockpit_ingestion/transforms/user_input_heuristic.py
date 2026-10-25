"""Value, costs and risk level of an initiative entered through the input form
(UserInput_Initiatives_Extract).

Unlike the sheet initiatives (transforms.value_heuristic / risk_heuristic),
nothing is guessed from free text here: the form asks for the drivers the
value-sizing formulas actually use, and for the criteria the
Rahmenbetriebsvereinbarung KI grades by. Same factors and constants as the
heuristic, so both kinds of initiatives are comparable:

- Efficiency     = CasesPerYear x HoursSavedPerCase x HOURLY_RATE_EUR
- Quality        = CasesPerYear x ErrorRateBefore x ErrorsAvoided x CostPerError
- Risk reduction = RiskEventsPerYear x EventsAvoided x CostPerEvent
- Strategic      = DelayEventsPerYear x CostOfDelayPerEvent x LeadTimeSaved
  (a lever with a missing driver counts as zero)
- Confidence from EstimateBasis, Delivery from DeliveryLikelihood
  (CONFIDENCE_FACTOR / DELIVERY_FACTOR); potential = sum x confidence x delivery
- Costs are expected costs like in the heuristic: the entered one-time and
  operating costs x DeliveryScore, one-time costs written off over
  DEPRECIATION_YEARS.

Risk level, first matching rule wins:
  ProhibitedPractice                                         -> 5
  DecisionsOnEmployees = automated or ProfilingOfIndividuals -> 4
  EmployeePersonalData = yes, PerformanceOrBehaviourControl
    or DecisionsOnEmployees = prepares                       -> 3
  EmployeePersonalData = pseudonymised or ChangesEmployeeWorkflows -> 2
  otherwise                                                  -> 1
Level 5 is set here (unlike the heuristic) because the form states it
explicitly; the agreement prohibits such systems, so it needs a review.
"""
from __future__ import annotations

import datetime
import re
from collections.abc import Mapping
from dataclasses import dataclass

from ai_cockpit_ingestion.transforms.risk_heuristic import RiskEstimate
from ai_cockpit_ingestion.transforms.value_heuristic import (
    CONFIDENCE_FACTOR,
    DELIVERY_FACTOR,
    DEPRECIATION_YEARS,
    HOURLY_RATE_EUR,
)

CONFIDENCE_BY_ESTIMATE_BASIS = {"rough": "Low", "benchmark": "Medium", "measured": "High"}
DELIVERY_BY_LIKELIHOOD = {"low": "Low", "medium": "Medium", "high": "High"}


@dataclass(frozen=True)
class UserInputValue:
    efficiency_eur: float
    quality_eur: float
    risk_reduction_eur: float
    strategic_eur: float
    confidence_score: float
    delivery_score: float
    one_time_costs: float
    operating_costs: float
    depreciation_years: int

    @property
    def hypothetical_eur(self) -> float:
        return self.efficiency_eur + self.quality_eur + self.risk_reduction_eur + self.strategic_eur


def _product(record: Mapping[str, object], *columns: str, factor: float = 1.0) -> float:
    values = [record.get(c) for c in columns]
    if any(v is None for v in values):
        return 0.0
    result = factor
    for v in values:
        result *= float(v)
    return result


def estimate_user_input_value(record: Mapping[str, object]) -> UserInputValue:
    delivery_score = DELIVERY_FACTOR[DELIVERY_BY_LIKELIHOOD[record["DeliveryLikelihood"]]]
    return UserInputValue(
        efficiency_eur=_product(record, "CasesPerYear", "HoursSavedPerCase", factor=HOURLY_RATE_EUR),
        quality_eur=_product(record, "CasesPerYear", "ErrorRateBefore", "ErrorsAvoided", "CostPerError"),
        risk_reduction_eur=_product(record, "RiskEventsPerYear", "EventsAvoided", "CostPerEvent"),
        strategic_eur=_product(record, "DelayEventsPerYear", "CostOfDelayPerEvent", "LeadTimeSaved"),
        confidence_score=CONFIDENCE_FACTOR[CONFIDENCE_BY_ESTIMATE_BASIS[record["EstimateBasis"]]],
        delivery_score=delivery_score,
        one_time_costs=float(record["OneTimeCosts"]) * delivery_score,
        operating_costs=float(record["OperatingCosts"]) * delivery_score,
        depreciation_years=DEPRECIATION_YEARS,
    )


def user_input_risk_level(record: Mapping[str, object]) -> RiskEstimate:
    if record["ProhibitedPractice"]:
        return RiskEstimate(5, "prohibited practice (emotion recognition, lie detection, not traceable)")
    if record["DecisionsOnEmployees"] == "automated":
        return RiskEstimate(4, "automated decisions about employees")
    if record["ProfilingOfIndividuals"]:
        return RiskEstimate(4, "profiling of individuals")
    if record["EmployeePersonalData"] == "yes":
        return RiskEstimate(3, "employee personal data")
    if record["PerformanceOrBehaviourControl"]:
        return RiskEstimate(3, "suitable for performance or behaviour control")
    if record["DecisionsOnEmployees"] == "prepares":
        return RiskEstimate(3, "prepares decisions about employees")
    if record["EmployeePersonalData"] == "pseudonymised":
        return RiskEstimate(2, "pseudonymised employee data")
    if record["ChangesEmployeeWorkflows"]:
        return RiskEstimate(2, "changes employees' workflows")
    return RiskEstimate(1, "no impact on employees")


_QUARTER = re.compile(r"^Q([1-4]) (\d{4})$")


def quarter_start(label: str | None) -> datetime.datetime | None:
    """'Q2 2027' -> 2027-04-01 (the table's CHECK constraint guarantees the format)."""
    match = _QUARTER.match(label or "")
    return datetime.datetime(int(match.group(2)), (int(match.group(1)) - 1) * 3 + 1, 1) if match else None
