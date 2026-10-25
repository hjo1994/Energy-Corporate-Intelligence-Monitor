from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Annotated, Literal

from eg_auth.fastapi import UserInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app import derived
from app.auth import authorizer
from app.db import get_session, get_write_session
from app.derived import annual_cost_sql, hypothetical_value_sql, potential_value_sql
from app.models import (
    BusinessTransaction,
    Initiative,
    Owner,
    RiskClassification,
    SolutionType,
    UserInputRecord,
    ValueType,
)
from app.schemas import (
    InitiativeIn,
    InitiativeOut,
    InitiativePage,
    RiskClassificationCount,
    StageCount,
    Summary,
)
from app.user_input import key_hash, provisional_values, quarter_start, risk_level

# Initiatives no longer in their source sheet are kept (soft delete) but hidden by default.
ACTIVE = Initiative.is_active.is_(True)

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
    include_inactive: bool = False,
) -> list:
    conditions = [] if include_inactive else [ACTIVE]
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
    include_inactive: Annotated[
        bool, Query(description="Also initiatives no longer in their source sheet (soft-deleted)")
    ] = False,
    include_pending: Annotated[
        bool,
        Query(description="Also initiatives submitted through the input form but not yet processed "
              "(status 'pending', provisional values); they come after all others, on the last page"),
    ] = True,
    sort: SortField = "name",
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InitiativePage:
    conditions = _conditions(
        stage, business_unit, department, owner_id, solution_type_id, value_type_id,
        risk_classification_id, search, include_inactive,
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

    total = total or 0
    if not include_pending:
        return InitiativePage(items=items, total=total, limit=limit, offset=offset)

    # Pending ones come after the silver result, so paging over both stays consistent.
    pending = [
        p for p in pending_initiatives(session)
        if _pending_matches(p, stage, business_unit, department, owner_id, solution_type_id,
                            value_type_id, risk_classification_id, search)
    ]
    start = max(0, offset - total)
    end = max(0, offset + limit - total)
    page = [InitiativeOut.model_validate(i) for i in items] + pending[start:end]
    return InitiativePage(items=page[:limit], total=total + len(pending), limit=limit, offset=offset)


def _unprocessed_records():
    processed = select(BusinessTransaction.bronze_id).where(
        BusinessTransaction.bronze_table_name == UserInputRecord.__tablename__
    )
    return select(UserInputRecord).where(UserInputRecord.id.not_in(processed))


def pending_initiatives(session: Session) -> list[InitiativeOut]:
    """Input-form records the DAG has not turned into an initiative yet, with provisional values."""
    records = session.scalars(
        _unprocessed_records()
        .options(joinedload(UserInputRecord.owner), joinedload(UserInputRecord.value_type),
                 joinedload(UserInputRecord.solution_type))
        .order_by(UserInputRecord.id)
    ).all()
    if not records:
        return []
    risks = {r.id: r for r in session.scalars(select(RiskClassification))}
    return [_pending_out(r, risks) for r in records]


def _pending_out(r: UserInputRecord, risks: dict[int, RiskClassification]) -> InitiativeOut:
    values = provisional_values(r)
    level = risk_level(r)
    v = SimpleNamespace(**values)  # derived.* only read these attributes
    return InitiativeOut.model_validate(
        {
            "id": -r.id,
            "name": r.name,
            "description": r.description,
            "stage": r.stage,
            "date_start": quarter_start(r.date_start),
            "date_delivery": quarter_start(r.date_delivery),
            **values,
            "solution_complexity_score": float(r.solution_complexity_score),
            "hypothetical_value_eur": derived.hypothetical_value(v),
            "potential_value_eur": derived.potential_value(v),
            "annual_cost_eur": derived.annual_cost(v),
            "owner": r.owner,
            "solution_type": r.solution_type,
            "value_type": r.value_type,
            "risk_classification": risks.get(level) or {"id": level, "name": str(level)},
            "is_active": True,
            "status": "pending",
            "user_input_id": r.id,
            "business_transaction_id": None,
        }
    )


def _pending_matches(p: InitiativeOut, stage, business_unit, department, owner_id, solution_type_id,
                     value_type_id, risk_classification_id, search) -> bool:
    term = (search or "").strip().lower()
    return (
        (not stage or p.stage in stage)
        and (not business_unit or (p.owner is not None and p.owner.category in business_unit))
        and (not department or (p.owner is not None and p.owner.department in department))
        and (owner_id is None or (p.owner is not None and p.owner.id == owner_id))
        and (solution_type_id is None or (p.solution_type is not None and p.solution_type.id == solution_type_id))
        and (value_type_id is None or (p.value_type is not None and p.value_type.id == value_type_id))
        and (not risk_classification_id or p.risk_classification.id in risk_classification_id)
        and (not term or term in p.name.lower() or term in (p.description or "").lower())
    )


@router.post("", response_model=InitiativeOut, status_code=201)
def create_initiative(
    body: InitiativeIn,
    user: Annotated[UserInfo, authorizer()],
    session: Annotated[Session, Depends(get_write_session)],
) -> InitiativeOut:
    """New initiative from the input form: stored in the bronze table UserInput_Initiatives_Extract
    and returned as "pending" with provisional values. The binding values follow within about a
    minute: the sensor of the DAG bronze_to_silver_user_input picks the record up."""
    owner = session.get(Owner, body.owner_id)
    if owner is None:
        raise HTTPException(status_code=422, detail="Unknown owner")
    if session.get(ValueType, body.value_type_id) is None:
        raise HTTPException(status_code=422, detail="Unknown flagship (value type)")
    if session.get(SolutionType, body.solution_type_id) is None:
        raise HTTPException(status_code=422, detail="Unknown solution type")

    key = key_hash(owner.category or "", body.name)
    business_unit = owner.category or "no business unit"
    if session.scalar(select(Initiative.id).where(Initiative.key_hash == key)) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"An initiative named “{body.name}” already exists in {business_unit}. "
            "Choose another name or edit the existing one in its source.",
        )
    for pending in session.scalars(_unprocessed_records().options(joinedload(UserInputRecord.owner))):
        if key_hash(pending.owner.category or "", pending.name) == key:
            raise HTTPException(
                status_code=409,
                detail=f"An initiative named “{body.name}” was just submitted for {business_unit} "
                "and is still being processed.",
            )

    record = UserInputRecord(
        **body.model_dump(),
        timestamp=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
        source_file_id="user-input",
        submitted_by=user.name,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    risks = {r.id: r for r in session.scalars(select(RiskClassification))}
    return _pending_out(record, risks)


@router.get("/summary", response_model=Summary)
def summary(session: Annotated[Session, Depends(get_session)]) -> Summary:
    total = session.scalar(select(func.count(Initiative.id)).where(ACTIVE)) or 0
    by_stage = session.execute(
        select(Initiative.stage, func.count(Initiative.id))
        .where(ACTIVE)
        .group_by(Initiative.stage)
        .order_by(func.count(Initiative.id).desc(), Initiative.stage)
    ).all()
    by_risk = session.execute(
        select(RiskClassification.id, RiskClassification.name, func.count(Initiative.id))
        .join(Initiative, Initiative.risk_classification_id == RiskClassification.id)
        .where(ACTIVE)
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
        ).where(ACTIVE)
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
            select(func.avg(Initiative.solution_complexity_score)).where(ACTIVE)
        ),
        without_owner=session.scalar(
            select(func.count(Initiative.id)).where(ACTIVE, Initiative.owner_id.is_(None))
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
