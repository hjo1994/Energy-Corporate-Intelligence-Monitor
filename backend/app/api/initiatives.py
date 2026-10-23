from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.auth import authorizer
from app.db import get_session
from app.derived import annual_cost_sql, hypothetical_value_sql, potential_value_sql
from app.models import Initiative, Owner, RiskClassification
from app.schemas import InitiativeOut, InitiativePage, RiskClassificationCount, StageCount, Summary

router = APIRouter(prefix="/api/initiatives", tags=["initiatives"], dependencies=[authorizer()])

SortField = Literal[
    "name",
    "stage",
    "potential_value_eur",
    "hypothetical_value_eur",
    "annual_cost_eur",
    "solution_complexity_score",
    "risk_classification",
    "date_start",
    "date_delivery",
]
_SORT_COLUMNS = {
    "name": Initiative.name,
    "stage": Initiative.stage,
    "potential_value_eur": potential_value_sql,
    "hypothetical_value_eur": hypothetical_value_sql,
    "annual_cost_eur": annual_cost_sql,
    "solution_complexity_score": Initiative.solution_complexity_score,
    "risk_classification": Initiative.risk_classification_id,
    "date_start": Initiative.date_start,
    "date_delivery": Initiative.date_delivery,
}


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _conditions(
    stage: list[str] | None,
    business_unit: list[str] | None,
    department: list[str] | None,
    owner_id: int | None,
    solution_type_id: int | None,
    value_type_id: int | None,
    risk_classification_id: list[int] | None,
    search: str | None,
) -> list:
    conditions = []
    if stage:
        conditions.append(Initiative.stage.in_(stage))
    if business_unit:
        conditions.append(Owner.category.in_(business_unit))
    if department:
        conditions.append(Owner.department.in_(department))
    if owner_id is not None:
        conditions.append(Initiative.owner_id == owner_id)
    if solution_type_id is not None:
        conditions.append(Initiative.solution_type_id == solution_type_id)
    if value_type_id is not None:
        conditions.append(Initiative.value_type_id == value_type_id)
    if risk_classification_id:
        conditions.append(Initiative.risk_classification_id.in_(risk_classification_id))
    if search and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        conditions.append(
            or_(
                Initiative.name.ilike(pattern, escape="\\"),
                Initiative.description.ilike(pattern, escape="\\"),
            )
        )
    return conditions


@router.get("", response_model=InitiativePage)
def list_initiatives(
    session: Annotated[Session, Depends(get_session)],
    stage: Annotated[list[str] | None, Query()] = None,
    business_unit: Annotated[list[str] | None, Query(description="Owner.category")] = None,
    department: Annotated[list[str] | None, Query()] = None,
    owner_id: int | None = None,
    solution_type_id: int | None = None,
    value_type_id: int | None = None,
    risk_classification_id: Annotated[list[int] | None, Query()] = None,
    search: Annotated[str | None, Query(description="Substring in name/description")] = None,
    sort: SortField = "name",
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InitiativePage:
    conditions = _conditions(
        stage, business_unit, department, owner_id, solution_type_id, value_type_id,
        risk_classification_id, search,
    )

    total = session.scalar(
        select(func.count(Initiative.id)).outerjoin(Owner).where(*conditions)
    )

    column = _SORT_COLUMNS[sort]
    ordering = column.desc() if order == "desc" else column.asc()
    items = session.scalars(
        select(Initiative)
        .outerjoin(Owner)
        .where(*conditions)
        .options(
            joinedload(Initiative.owner),
            joinedload(Initiative.solution_type),
            joinedload(Initiative.value_type),
            joinedload(Initiative.risk_classification),
        )
        # `IS NULL` first = missing values last in either direction. Portable on purpose: the
        # cluster's SQLite 3.26 has no NULLS LAST (needs 3.30) and MySQL never had it.
        .order_by(column.is_(None), ordering, Initiative.id)
        .limit(limit)
        .offset(offset)
    ).all()

    return InitiativePage(items=items, total=total or 0, limit=limit, offset=offset)


@router.get("/summary", response_model=Summary)
def summary(session: Annotated[Session, Depends(get_session)]) -> Summary:
    total = session.scalar(select(func.count(Initiative.id))) or 0
    by_stage = session.execute(
        select(Initiative.stage, func.count(Initiative.id))
        .group_by(Initiative.stage)
        .order_by(func.count(Initiative.id).desc(), Initiative.stage)
    ).all()
    by_risk = session.execute(
        select(RiskClassification.id, RiskClassification.name, func.count(Initiative.id))
        .join(Initiative, Initiative.risk_classification_id == RiskClassification.id)
        .group_by(RiskClassification.id, RiskClassification.name)
        .order_by(RiskClassification.id)
    ).all()
    with_potential, total_potential, average_potential, total_hypothetical, total_cost = session.execute(
        select(
            func.count(potential_value_sql),
            func.sum(potential_value_sql),
            func.avg(potential_value_sql),
            func.sum(hypothetical_value_sql),
            func.sum(annual_cost_sql),
        )
    ).one()
    return Summary(
        total=total,
        by_stage=[StageCount(stage=s, count=c) for s, c in by_stage],
        by_risk_classification=[
            RiskClassificationCount(id=i, name=n, count=c) for i, n, c in by_risk
        ],
        with_potential_value=with_potential,
        without_potential_value=total - with_potential,
        total_potential_value_eur=total_potential,
        average_potential_value_eur=average_potential,
        total_hypothetical_value_eur=total_hypothetical,
        total_annual_cost_eur=total_cost,
        average_solution_complexity_score=session.scalar(
            select(func.avg(Initiative.solution_complexity_score))
        ),
        without_owner=session.scalar(
            select(func.count(Initiative.id)).where(Initiative.owner_id.is_(None))
        )
        or 0,
    )


@router.get("/{initiative_id}", response_model=InitiativeOut)
def get_initiative(
    initiative_id: int, session: Annotated[Session, Depends(get_session)]
) -> Initiative:
    initiative = session.scalars(
        select(Initiative)
        .where(Initiative.id == initiative_id)
        .options(
            joinedload(Initiative.owner),
            joinedload(Initiative.solution_type),
            joinedload(Initiative.value_type),
            joinedload(Initiative.risk_classification),
        )
    ).first()
    if initiative is None:
        raise HTTPException(status_code=404, detail="Initiative nicht gefunden")
    return initiative
