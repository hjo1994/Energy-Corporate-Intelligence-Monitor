"""Gold assessment of one use case from its current silver version
(models.AssessedInitiative), deterministic:

- Complete = all value buckets (efficiency, quality, risk reduction,
  strategic), ConfidenceScore and DeliveryScore, the six risk answers,
  OneTimeCosts and RunningCosts are set.
  Only complete use cases are assessed.
- PotentialValue = (efficiency + quality + risk reduction + strategic)
  x ConfidenceScore x DeliveryScore, EUR per year.
- RealizedValue:
  - real values reported (MeasuredBenefits): MeasuredBenefits - ActualCosts
    (ActualCosts = ActualCapex + ActualOpex, missing = 0);
  - otherwise, once DateDelivery has passed: PotentialValue x runtime -
    (OneTimeCosts + RunningCosts x runtime), runtime = years since DateDelivery;
  - otherwise NULL.
- Risk level from the six answers, same rules as the UI form
  (transforms.user_input_heuristic.user_input_risk_level).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from ai_cockpit_ingestion.transforms.user_input_heuristic import user_input_risk_level

BUCKETS = ("efficiency_score_eur", "quality_score_eur", "risk_reduction_score_eur", "strategic_value_score_eur")
RISK_ANSWERS = {
    "EmployeePersonalData": "employee_personal_data",
    "PerformanceOrBehaviourControl": "performance_or_behaviour_control",
    "DecisionsOnEmployees": "decisions_on_employees",
    "ProfilingOfIndividuals": "profiling_of_individuals",
    "ChangesEmployeeWorkflows": "changes_employee_workflows",
    "ProhibitedPractice": "prohibited_practice",
}
FACTORS = ("confidence_score", "delivery_score")
COSTS = ("one_time_costs", "running_costs")
MANDATORY = (*BUCKETS, *FACTORS, *RISK_ANSWERS.values(), *COSTS)
DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class Assessment:
    potential_value: float
    realized_value: float | None
    risk_level: int
    runtime_based: bool  # RealizedValue depends on today (recomputed daily)


def missing_mandatory(version) -> list[str]:
    return [a for a in MANDATORY if getattr(version, a) is None]


def is_complete(version) -> bool:
    return not missing_mandatory(version)


def runtime_years(date_delivery: datetime.datetime | None, today: datetime.date) -> float | None:
    """Years since delivery, None before delivery (or without a date)."""
    if date_delivery is None or date_delivery.date() > today:
        return None
    return (today - date_delivery.date()).days / DAYS_PER_YEAR


def assess(version, today: datetime.date) -> Assessment:
    hypothetical = sum(getattr(version, b) for b in BUCKETS)
    potential = hypothetical * version.confidence_score * version.delivery_score

    runtime_based = False
    if version.measured_benefits is not None:
        realized = version.measured_benefits - (version.actual_costs or 0.0)
    else:
        runtime = runtime_years(version.date_delivery, today)
        if runtime is None:
            realized = None
        else:
            realized = potential * runtime - (version.one_time_costs + version.running_costs * runtime)
            runtime_based = True

    answers = {column: getattr(version, attribute) for column, attribute in RISK_ANSWERS.items()}
    return Assessment(potential, realized, user_input_risk_level(answers).level, runtime_based)

