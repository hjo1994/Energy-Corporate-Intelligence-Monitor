from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.auth import authorizer
from app.db import get_session
from app.models import Initiative, Owner
from app.schemas import InitiativeOut, InitiativePage, StatusCount, Summary

router = APIRouter(prefix="/api/initiatives", tags=["initiatives"], dependencies=[authorizer()])

SortField = Literal[
    "name",
    "status",
    "value_score",
    "solution_complexity_score",
    "date_start",
    "date_delivery",
]
_SORT_COLUMNS = {
    "name": Initiative.name,
    "status": Initiative.status,
    "value_score": Initiative.value_score,
    "solution_complexity_score": Initiative.solution_complexity_score,
    "date_start": Initiative.date_start,
    "date_delivery": Initiative.date_delivery,
}


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _conditions(
    status: list[str] | None,
    business_unit: list[str] | None,
    department: list[str] | None,
    owner_id: int | None,
    solution_type_id: int | None,
    value_type_id: int | None,
    search: str | None,
) -> list:
    conditions = []
    if status:
        conditions.append(Initiative.status.in_(status))
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
    status: Annotated[list[str] | None, Query()] = None,
    business_unit: Annotated[list[str] | None, Query(description="Owner.category")] = None,
    department: Annotated[list[str] | None, Query()] = None,
    owner_id: int | None = None,
    solution_type_id: int | None = None,
    value_type_id: int | None = None,
    search: Annotated[str | None, Query(description="Substring in name/description")] = None,
    sort: SortField = "name",
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InitiativePage:
    conditions = _conditions(
        status, business_unit, department, owner_id, solution_type_id, value_type_id, search
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
    by_status = session.execute(
        select(Initiative.status, func.count(Initiative.id))
        .group_by(Initiative.status)
        .order_by(func.count(Initiative.id).desc(), Initiative.status)
    ).all()
    with_value = session.scalar(
        select(func.count(Initiative.id)).where(Initiative.value_score.is_not(None))
    ) or 0
    return Summary(
        total=total,
        by_status=[StatusCount(status=s, count=c) for s, c in by_status],
        with_value_score=with_value,
        without_value_score=total - with_value,
        average_value_score=session.scalar(select(func.avg(Initiative.value_score))),
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
        )
    ).first()
    if initiative is None:
        raise HTTPException(status_code=404, detail="Initiative nicht gefunden")
    return initiative
