"""Reference/lookup data, e.g. for building filter controls."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import authorizer
from app.db import get_session
from app.models import Initiative, Owner, RiskClassification, SolutionType, ValueType
from app.schemas import BusinessUnitCount, OwnerOut, RiskClassificationOut, StageCount, TypeOut

router = APIRouter(prefix="/api", tags=["reference"], dependencies=[authorizer()])


@router.get("/owners", response_model=list[OwnerOut])
def list_owners(
    session: Annotated[Session, Depends(get_session)],
    business_unit: Annotated[str | None, Query(description="Owner.category")] = None,
) -> list[Owner]:
    stmt = select(Owner).order_by(Owner.name, Owner.id)
    if business_unit:
        stmt = stmt.where(Owner.category == business_unit)
    return list(session.scalars(stmt))


@router.get("/solution-types", response_model=list[TypeOut])
def list_solution_types(session: Annotated[Session, Depends(get_session)]) -> list[SolutionType]:
    return list(session.scalars(select(SolutionType).order_by(SolutionType.name)))


@router.get("/value-types", response_model=list[TypeOut])
def list_value_types(session: Annotated[Session, Depends(get_session)]) -> list[ValueType]:
    return list(session.scalars(select(ValueType).order_by(ValueType.name)))


@router.get("/business-units", response_model=list[BusinessUnitCount])
def list_business_units(
    session: Annotated[Session, Depends(get_session)],
) -> list[BusinessUnitCount]:
    """Distinct Owner.category values with their initiative count.
    Initiatives without an owner belong to no business unit and are not counted here.
    """
    rows = session.execute(
        select(Owner.category, func.count(Initiative.id))
        .outerjoin(Initiative, Initiative.owner_id == Owner.id)
        .group_by(Owner.category)
        .order_by(Owner.category)
    ).all()
    return [BusinessUnitCount(name=name, count=count) for name, count in rows]


@router.get("/stages", response_model=list[StageCount])
def list_stages(session: Annotated[Session, Depends(get_session)]) -> list[StageCount]:
    rows = session.execute(
        select(Initiative.stage, func.count(Initiative.id))
        .group_by(Initiative.stage)
        .order_by(func.count(Initiative.id).desc(), Initiative.stage)
    ).all()
    return [StageCount(stage=s, count=c) for s, c in rows]


@router.get("/risk-classifications", response_model=list[RiskClassificationOut])
def list_risk_classifications(
    session: Annotated[Session, Depends(get_session)],
) -> list[RiskClassification]:
    """All five levels of the Rahmenbetriebsvereinbarung KI, including unused ones."""
    return list(session.scalars(select(RiskClassification).order_by(RiskClassification.id)))
