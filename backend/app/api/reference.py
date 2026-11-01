"""Reference/lookup data, e.g. for building filter controls."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.auth import authorizer
from app.config import initiative_input_enabled
from app.db import get_session
from app import schemas
from app.models import Initiative, Owner, RiskClassification, SolutionType, ValueType, current_version_ids
from app.schemas import BusinessUnitCount, OwnerOut, RiskClassificationOut, StageCount, TypeOut
from app.user_input import RUNNING_COST_RANGES

# the current version of every use case that is still active
_CURRENT_ACTIVE = (Initiative.id.in_(current_version_ids()), Initiative.is_active.is_(True))

router = APIRouter(prefix="/api", tags=["reference"], dependencies=[authorizer()])


@router.get("/owners", response_model=list[OwnerOut])
def list_owners(
    session: Annotated[Session, Depends(get_session)],
    business_unit: Annotated[str | None, Query(description="Owner.category")] = None,
    search: Annotated[str | None, Query(description="Substring in name, department or e-mail (person picker)")] = None,
    limit: Annotated[int | None, Query(ge=1, le=500)] = None,
) -> list[Owner]:
    stmt = select(Owner).order_by(Owner.name, Owner.id)
    if business_unit:
        stmt = stmt.where(Owner.category == business_unit)
    if search and search.strip():
        pattern = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(Owner.name.ilike(pattern, escape="\\"), Owner.department.ilike(pattern, escape="\\"),
                              Owner.email.ilike(pattern, escape="\\")))
    if limit:
        stmt = stmt.limit(limit)
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
        .outerjoin(Initiative, and_(Initiative.owner_id == Owner.id, *_CURRENT_ACTIVE))
        .group_by(Owner.category)
        .order_by(Owner.category)
    ).all()
    return [BusinessUnitCount(name=name, count=count) for name, count in rows]


@router.get("/stages", response_model=list[StageCount])
def list_stages(session: Annotated[Session, Depends(get_session)]) -> list[StageCount]:
    rows = session.execute(
        select(Initiative.stage, func.count(Initiative.id))
        .where(*_CURRENT_ACTIVE)
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


@router.get("/features")
def features() -> dict[str, bool]:
    """Feature switches for the frontend (AI_COCKPIT_ENABLE_INITIATIVE_INPUT)."""
    return {"initiative_input": initiative_input_enabled()}


def _options(values) -> list[dict[str, str]]:
    return [{"value": v, "label": v} for v in values]


@router.get("/form-options")
def form_options() -> dict:
    """Choice lists of forms 1 and 2 (the same values the database accepts).
    Owners, flagships (value types) and solution types come from their own endpoints."""
    return {
        "stages": _options(schemas.STAGES),
        "stagegates": _options(schemas.STAGEGATES),
        "ai_layers": _options(schemas.AI_LAYERS),
        "running_cost_ranges": [{"value": k, "label": label, "amount": amount}
                                for k, (label, amount) in RUNNING_COST_RANGES.items()],
        "estimate_bases": _options(schemas.ESTIMATE_BASES),
        "delivery_likelihoods": _options(schemas.DELIVERY_LIKELIHOODS),
        "employee_personal_data": _options(schemas.EMPLOYEE_PERSONAL_DATA),
        "decisions_on_employees": _options(schemas.DECISIONS_ON_EMPLOYEES),
        "enabling_teams": _options(schemas.ENABLING_TEAMS),
        "complexity_solidities": _options(schemas.COMPLEXITY_SOLIDITIES),
        "eu_ai_act_classes": _options(schemas.EU_AI_ACT_CLASSES),
        "eu_ai_act_roles": _options(schemas.EU_AI_ACT_ROLES),
        "works_council_risk_classes": _options(schemas.WORKS_COUNCIL_RISK_CLASSES),
        "capability_directions": _options(schemas.CAPABILITY_DIRECTIONS),
        "applicable_to": _options(schemas.APPLICABLE_TO),
        # value domain (27 entries) and autonomy level: free text until the lists are final
    }
