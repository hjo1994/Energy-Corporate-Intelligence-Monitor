from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class InitiativeOut(_Out):
    id: int
    name: str
    description: str | None
    stage: str
    date_start: datetime | None
    date_delivery: datetime | None
    value_score: float | None
    solution_complexity_score: float | None
    owner: OwnerOut | None
    solution_type: TypeOut | None
    value_type: TypeOut | None


class InitiativePage(BaseModel):
    items: list[InitiativeOut]
    total: int
    limit: int
    offset: int


class StageCount(BaseModel):
    stage: str
    count: int


class BusinessUnitCount(BaseModel):
    name: str | None
    count: int


class Summary(BaseModel):
    total: int
    by_stage: list[StageCount]
    with_value_score: int
    without_value_score: int
    average_value_score: float | None
    average_solution_complexity_score: float | None
    without_owner: int
