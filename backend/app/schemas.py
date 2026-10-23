from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

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

    @model_validator(mode="before")
    @classmethod
    def _add_derived(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        values = {name: getattr(data, name) for name in cls.model_fields if hasattr(data, name)}
        values["hypothetical_value_eur"] = derived.hypothetical_value(data)
        values["potential_value_eur"] = derived.potential_value(data)
        values["annual_cost_eur"] = derived.annual_cost(data)
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
