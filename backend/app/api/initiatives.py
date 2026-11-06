"""Dashboard endpoints (list, summary, detail) and form 1 (POST).

The dashboard reads the current silver version of every use case with its gold
assessment (AssessedInitiatives): potential value, realized value and risk
level come from gold. `id` is the UseCaseID. Use cases not assessed yet are
listed too, marked (`processing`, `provisional`), and so are ideas created in
the UI that the pipeline has not processed yet (appended after all others,
id = −record ID), see app/use_cases.py.
"""
from __future__ import annotations

import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth import CurrentUser, authorizer
from app.config import initiative_input_enabled
from app.db import get_session, get_write_session
from app.derived import annual_cost_sql, hypothetical_value_sql
from app.lifecycle import gate_dates, stage_problems
from app.users import owner_for_create
from app.models import (
    AppUser,
    GATE_DATE_FIELDS,
    AssessedInitiative,
    Initiative,
    Owner,
    RiskClassification,
    UserAction,
    ValueType,
    current_version_ids,
)
from app.pipeline import notify_user_action
from app.schemas import (
    InitiativeIn,
    InitiativeOut,
    InitiativePage,
    RiskClassificationCount,
    StageCount,
    Summary,
    current_stage,
)
from app.use_cases import (
    Lookups,
    load_state,
    load_states,
    pending_create_state,
    table_exists,
    today,
    unprocessed_actions,
    with_refs,
)
from app.user_input import RUNNING_COST_RANGES, key_hash, utcnow

CURRENT = Initiative.id.in_(current_version_ids())
# Use cases no longer in their source sheet are kept (soft delete) but hidden by default.
ACTIVE = Initiative.is_active.is_(True)
GOLD = AssessedInitiative

router = APIRouter(prefix="/api/initiatives", tags=["initiatives"], dependencies=[authorizer()])

SortField = Literal[
    "name",
    "stage",
    "potential_value_eur",
    "realized_value_eur",
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
    "potential_value_eur": GOLD.potential_value,
    "realized_value_eur": GOLD.realized_value,
    "hypothetical_value_eur": hypothetical_value_sql,
    "annual_cost_eur": annual_cost_sql,
    "solution_complexity_score": Initiative.solution_complexity_score,
    "risk_classification": GOLD.risk_classification_id,
    "date_start": Initiative.date_start,
    "date_delivery": Initiative.date_delivery,
}


def _base(*columns):
    return (
        select(*columns)
        .select_from(Initiative)
        .outerjoin(GOLD, GOLD.use_case_id == Initiative.use_case_id)
        .outerjoin(Owner, Owner.id == Initiative.owner_id)
        .where(CURRENT)
    )


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _conditions(stage, business_unit, department, owner_id, solution_type_id, value_type_id,
                risk_classification_id, approval_status, search, include_inactive=False) -> list:
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
        conditions.append(GOLD.risk_classification_id.in_(risk_classification_id))
    if approval_status:
        conditions.append(Initiative.status.in_(approval_status))
    if search and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        conditions.append(or_(Initiative.name.ilike(pattern, escape="\\"),
                              Initiative.description.ilike(pattern, escape="\\")))
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
    risk_classification_id: Annotated[list[int] | None, Query(description="gold risk level")] = None,
    approval_status: Annotated[list[Literal["pending", "approved", "rejected"]] | None, Query()] = None,
    search: Annotated[str | None, Query(description="Substring in name/description")] = None,
    include_inactive: Annotated[
        bool, Query(description="Also use cases no longer in their source sheet (soft-deleted)")
    ] = False,
    include_pending: Annotated[
        bool,
        Query(description="Also ideas created in the UI but not processed yet (status 'pending', "
              "provisional values); they come after all others, on the last page"),
    ] = True,
    sort: SortField = "name",
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InitiativePage:
    stage = [current_stage(s) for s in stage] if stage else None  # ?stage=Idea still finds Ideation
    filters = (stage, business_unit, department, owner_id, solution_type_id, value_type_id,
               risk_classification_id, approval_status, search)
    conditions = _conditions(*filters, include_inactive)
    total = session.scalar(_base(func.count(Initiative.id)).where(*conditions)) or 0

    column = _SORT_COLUMNS[sort]
    ordering = column.desc() if order == "desc" else column.asc()
    page_ids = list(session.scalars(
        _base(Initiative.use_case_id)
        .where(*conditions)
        # `IS NULL` first = missing values last in either direction. Portable on purpose: the
        # cluster's SQLite 3.26 has no NULLS LAST (needs 3.30) and MySQL never had it.
        .order_by(column.is_(None), ordering, Initiative.use_case_id)
        .limit(limit)
        .offset(offset)
    ))
    lookups = Lookups(session)
    states = {s["id"]: s for s in load_states(session, page_ids, include_pending_creates=False)} if page_ids else {}
    items = [InitiativeOut.model_validate(with_refs(states[i], lookups)) for i in page_ids]
    if not include_pending:
        return InitiativePage(items=items, total=total, limit=limit, offset=offset)

    # Pending ones come after the silver result, so paging over both stays consistent.
    pending = [p for p in pending_initiatives(session, lookups) if _pending_matches(p, *filters)]
    start = max(0, offset - total)
    end = max(0, offset + limit - total)
    page = items + pending[start:end]
    return InitiativePage(items=page[:limit], total=total + len(pending), limit=limit, offset=offset)


def pending_initiatives(session: Session, lookups: Lookups) -> list[InitiativeOut]:
    """Ideas created in the UI that the DAG has not turned into a use case yet, with provisional values."""
    return [
        InitiativeOut.model_validate(with_refs(pending_create_state(a), lookups))
        for a in unprocessed_actions(session) if a.action_type == "create"
    ]


def _pending_matches(p: InitiativeOut, stage, business_unit, department, owner_id, solution_type_id,
                     value_type_id, risk_classification_id, approval_status, search) -> bool:
    term = (search or "").strip().lower()
    return (
        (not stage or p.stage in stage)
        and (not business_unit or (p.owner is not None and p.owner.category in business_unit))
        and (not department or (p.owner is not None and p.owner.department in department))
        and (owner_id is None or (p.owner is not None and p.owner.id == owner_id))
        and (solution_type_id is None or (p.solution_type is not None and p.solution_type.id == solution_type_id))
        and (value_type_id is None or (p.value_type is not None and p.value_type.id == value_type_id))
        and (not risk_classification_id
             or (p.risk_classification is not None and p.risk_classification.id in risk_classification_id))
        and (not approval_status or "pending" in approval_status)
        and (not term or term in p.name.lower() or term in (p.description or "").lower())
    )


def check_stage_gates(stage: str | None, dates: dict, day: datetime.date) -> None:
    """422 when the gate dates do not fit the stage (app/lifecycle.py)."""
    problems = stage_problems(stage, dates, day)
    if problems:
        raise HTTPException(status_code=422, detail=" ".join(problems))


def as_datetimes(fields: dict, names) -> None:
    for name in names:
        if isinstance(fields.get(name), datetime.date) and not isinstance(fields[name], datetime.datetime):
            fields[name] = datetime.datetime.combine(fields[name], datetime.time())



@router.post("", response_model=InitiativeOut, status_code=201)
def create_initiative(
    body: InitiativeIn,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_write_session)],
) -> InitiativeOut:
    """Form 1, a new AI idea: stored as a 'create' action in the bronze table UserActionExtracts
    and returned as "pending" with provisional values. Within about a minute the DAG
    bronze_to_silver_user_input turns it into a use case (approval status pending)."""
    if not initiative_input_enabled():
        raise HTTPException(status_code=403, detail="Adding initiatives is switched off on this installation.")
    if not table_exists(session):
        raise HTTPException(
            status_code=503,
            detail="Adding initiatives is not available yet: the pipeline has not created its table. "
            "Please try again in a few minutes.",
        )
    if user.user_id is None:
        raise HTTPException(status_code=503, detail="Your user could not be stored yet. Please try again in a minute.")
    if body.needs_gate_date > today():
        raise HTTPException(status_code=422, detail="The needs gate date cannot be in the future: it is the day it was passed.")
    if body.owner_user_id is not None and body.owner_user_id != user.user_id:  # another user chosen in form 1
        chosen = session.get(AppUser, body.owner_user_id)
        if chosen is None or not chosen.is_active:
            raise HTTPException(status_code=422, detail="Unknown user")
        owner = owner_for_create(session, chosen.id, chosen.name, body.business_unit)
        if owner is None:
            raise HTTPException(status_code=422, detail=f"Choose the business unit of {chosen.name}: they are not an owner yet.")
    else:  # the signed-in user
        owner = owner_for_create(session, user.user_id, user.sso_name, body.business_unit)
        if owner is None:
            raise HTTPException(status_code=422, detail="Choose your business unit: you are not an owner yet.")
    if session.get(ValueType, body.value_type_id) is None:
        raise HTTPException(status_code=422, detail="Unknown topic (value type)")

    key = key_hash(owner.category or "", body.name)
    business_unit = owner.category or "no business unit"
    if session.scalar(select(Initiative.id).where(Initiative.key_hash == key).limit(1)) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"An initiative named “{body.name}” already exists in {business_unit}. "
            "Choose another name or edit the existing one.",
        )
    owners = {o.id: o.category or "" for o in session.scalars(select(Owner))}
    for pending in unprocessed_actions(session):
        if pending.action_type == "create" and key_hash(owners.get(pending.owner_id, ""), pending.name) == key:
            raise HTTPException(
                status_code=409,
                detail=f"An initiative named “{body.name}” was just submitted for {business_unit} "
                "and is still being processed.",
            )

    values = body.model_dump(exclude={"running_cost_range", "business_unit", "owner_user_id"})
    check_stage_gates(body.stage, gate_dates(values), today())
    as_datetimes(values, GATE_DATE_FIELDS.values())
    record = UserAction(
        **values,
        operating_costs=RUNNING_COST_RANGES[body.running_cost_range][1],
        action_type="create",
        timestamp=utcnow(),
        source_file_id="user-input",
        submitted_by=user.name,
        submitted_by_user_id=user.user_id,
        owner_id=owner.id,
    )
    commit(session, record)
    return InitiativeOut.model_validate(with_refs(pending_create_state(record), Lookups(session)))


def commit(session: Session, record: UserAction) -> None:
    session.add(record)
    try:
        session.commit()
    except OperationalError as err:
        session.rollback()
        if "readonly" in str(err).lower() or "read-only" in str(err).lower():
            raise HTTPException(
                status_code=503,
                detail="The change could not be saved: the database is read-only for the API on this installation.",
            ) from err
        raise
    session.refresh(record)
    if isinstance(record, UserAction):
        notify_user_action()  # bronze_to_silver_user_input processes it within seconds


@router.get("/summary", response_model=Summary)
def summary(session: Annotated[Session, Depends(get_session)]) -> Summary:
    total = session.scalar(_base(func.count(Initiative.id)).where(ACTIVE)) or 0
    by_stage = session.execute(
        _base(Initiative.stage, func.count(Initiative.id))
        .where(ACTIVE)
        .group_by(Initiative.stage)
        .order_by(func.count(Initiative.id).desc(), Initiative.stage)
    ).all()
    by_risk = session.execute(
        _base(RiskClassification.id, RiskClassification.name, func.count(Initiative.id))
        .join(RiskClassification, RiskClassification.id == GOLD.risk_classification_id)
        .where(ACTIVE)
        .group_by(RiskClassification.id, RiskClassification.name)
        .order_by(RiskClassification.id)
    ).all()
    (with_potential, total_potential, average_potential, total_realized, total_hypothetical, total_cost,
     not_assessed, average_complexity, without_owner) = session.execute(
        _base(
            func.count(GOLD.potential_value),
            func.sum(GOLD.potential_value),
            func.avg(GOLD.potential_value),
            func.sum(GOLD.realized_value),
            func.sum(hypothetical_value_sql),
            func.sum(annual_cost_sql),
            # sum(case) instead of COUNT FILTER: the cluster's SQLite 3.26 has no FILTER clause
            func.sum(case((or_(GOLD.id.is_(None), GOLD.initiative_id != Initiative.id), 1), else_=0)),
            func.avg(Initiative.solution_complexity_score),
            func.sum(case((Initiative.owner_id.is_(None), 1), else_=0)),
        ).where(ACTIVE)
    ).one()
    return Summary(
        total=total,
        by_stage=[StageCount(stage=s, count=c) for s, c in by_stage],
        by_risk_classification=[RiskClassificationCount(id=i, name=n, count=c) for i, n, c in by_risk],
        with_potential_value=with_potential,
        without_potential_value=total - with_potential,
        not_assessed=not_assessed or 0,
        total_potential_value_eur=total_potential,
        average_potential_value_eur=average_potential,
        total_realized_value_eur=total_realized,
        total_hypothetical_value_eur=total_hypothetical,
        total_annual_cost_eur=total_cost,
        average_solution_complexity_score=average_complexity,
        without_owner=without_owner or 0,
    )


@router.get("/{initiative_id}", response_model=InitiativeOut)
def get_initiative(initiative_id: int, session: Annotated[Session, Depends(get_session)]) -> InitiativeOut:
    """One use case by UseCaseID (or a pending idea by −record ID)."""
    state = load_state(session, initiative_id, with_drivers=False)
    if state is None:
        raise HTTPException(status_code=404, detail="Initiative nicht gefunden")
    return InitiativeOut.model_validate(with_refs(state, Lookups(session)))
