from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app import derived


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OwnerOut(_Out):
    id: int
    name: str
    department: str | None
    category: str | None  # business unit


class TypeOut(_Out):
    id: int
    name: str
    description: str | None


class RiskClassificationRef(_Out):
    id: int
    name: str


class RiskClassificationOut(RiskClassificationRef):
    description: str | None
    derived_action: str | None


class InitiativeOut(_Out):
    id: int
    name: str
    description: str | None
    stage: str
    date_start: datetime | None
    date_delivery: datetime | None
    # value buckets and discount factors (estimates, EUR per year)
    efficiency_score_eur: float | None
    quality_score_eur: float | None
    risk_reduction_score_eur: float | None
    strategic_value_score_eur: float | None
    confidence_score: float | None
    delivery_score: float | None
    solution_complexity_score: float | None
    one_time_costs: float | None
    operating_costs: float | None
    depreciation_years: int | None
    # derived, see app/derived.py
    hypothetical_value_eur: float | None
    potential_value_eur: float | None
    annual_cost_eur: float | None
    owner: OwnerOut | None
    solution_type: TypeOut | None
    value_type: TypeOut | None
    risk_classification: RiskClassificationRef | None
    is_active: bool
    # "pending": submitted through the input form, not yet processed by the DAG — values are
    # provisional (same formulas) and `id` is the negative bronze record ID (`user_input_id`)
    status: Literal["active", "inactive", "pending"] = "active"
    user_input_id: int | None = None
    business_transaction_id: int | None

    @model_validator(mode="before")
    @classmethod
    def _add_derived(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        values = {name: getattr(data, name) for name in cls.model_fields if hasattr(data, name)}
        values["hypothetical_value_eur"] = derived.hypothetical_value(data)
        values["potential_value_eur"] = derived.potential_value(data)
        values["annual_cost_eur"] = derived.annual_cost(data)
        values["status"] = "active" if data.is_active else "inactive"
        return values


class InitiativePage(BaseModel):
    items: list[InitiativeOut]
    total: int
    limit: int
    offset: int


class StageCount(BaseModel):
    stage: str
    count: int


class RiskClassificationCount(BaseModel):
    id: int
    name: str
    count: int


class BusinessUnitCount(BaseModel):
    name: str | None
    count: int


class Summary(BaseModel):
    total: int
    by_stage: list[StageCount]
    by_risk_classification: list[RiskClassificationCount]
    with_potential_value: int
    without_potential_value: int
    total_potential_value_eur: float | None
    average_potential_value_eur: float | None
    total_hypothetical_value_eur: float | None
    total_annual_cost_eur: float | None
    average_solution_complexity_score: float | None
    without_owner: int


Quarter = Annotated[str, StringConstraints(pattern=r"^Q[1-4] \d{4}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Count = Annotated[float, Field(ge=0)]
Share = Annotated[float, Field(ge=0, le=1)]  # a percentage divided by 100

STAGES = ("Idea", "Exploration", "PoC", "MVP", "Implementation", "Production", "On hold", "Cancelled", "Unknown")

# Value levers and their drivers; at least one lever must be complete.
LEVERS = {
    "efficiency": ("cases_per_year", "hours_saved_per_case"),
    "quality": ("cases_per_year", "error_rate_before", "errors_avoided", "cost_per_error"),
    "risk_reduction": ("risk_events_per_year", "events_avoided", "cost_per_event"),
    "speed": ("delay_events_per_year", "cost_of_delay_per_event", "lead_time_saved"),
}


class InitiativeIn(BaseModel):
    """A new initiative from the input form; the same rules as the CHECK constraints of
    UserInput_Initiatives_Extract, plus: at least one complete value lever."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Text
    owner_id: int
    value_type_id: int
    solution_type_id: int
    stage: Literal[STAGES]  # type: ignore[valid-type]
    date_start: Quarter | None = None
    date_delivery: Quarter | None = None

    cases_per_year: Count | None = None
    hours_saved_per_case: Count | None = None
    error_rate_before: Share | None = None
    errors_avoided: Share | None = None
    cost_per_error: Count | None = None
    risk_events_per_year: Count | None = None
    events_avoided: Share | None = None
    cost_per_event: Count | None = None
    delay_events_per_year: Count | None = None
    cost_of_delay_per_event: Count | None = None
    lead_time_saved: Share | None = None

    estimate_basis: Literal["rough", "benchmark", "measured"]
    delivery_likelihood: Literal["low", "medium", "high"]
    solution_complexity_score: Annotated[int, Field(ge=1, le=9)]
    one_time_costs: Count
    operating_costs: Count

    employee_personal_data: Literal["no", "pseudonymised", "yes"]
    performance_or_behaviour_control: bool
    decisions_on_employees: Literal["none", "prepares", "automated"]
    profiling_of_individuals: bool
    changes_employee_workflows: bool
    prohibited_practice: bool

    @model_validator(mode="after")
    def _one_complete_lever(self) -> "InitiativeIn":
        if not any(all(getattr(self, f) is not None for f in fields) for fields in LEVERS.values()):
            raise ValueError("At least one value lever needs all of its drivers")
        return self
