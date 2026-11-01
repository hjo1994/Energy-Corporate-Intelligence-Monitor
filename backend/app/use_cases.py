"""The state of a use case as the UI sees it: the current silver version, its
gold assessment and the user actions the pipeline has not processed yet.

Every write goes to bronze first (UserActionExtracts) and reaches silver and
gold only after the DAGs have run (about a minute each). So that a user sees
their change at once, the read endpoints lay the unprocessed actions over the
current version, the same way the DAG will (app/user_input.py), and mark the
use case:

- processing "pending":         created in the UI, not in silver yet
                                (id = −record ID, cannot be edited or decided yet)
- processing "changes_pending": in silver, with unprocessed actions on top
- processing "not_assessed":    in silver, but gold has not assessed the current
                                version (incomplete, or silver_to_gold not run yet)
- processing "assessed":        gold has assessed the current version

Potential value and risk level come from gold when it has assessed the current
version and nothing is pending; otherwise they are computed provisionally with
the same formulas (`provisional` = True). The realized value only comes from gold.
"""
from __future__ import annotations

import datetime
from collections import defaultdict

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app import derived
from app.lifecycle import gate_dates, last_passed_gate, stage_problems
from app.models import (
    FORM2_FIELDS,
    GATE_DATE_FIELDS,
    RISK_ANSWERS,
    AssessedInitiative,
    BusinessTransaction,
    Initiative,
    Owner,
    RiskClassification,
    SolutionType,
    UserAction,
    ValueType,
    current_version_ids,
)
from app.user_input import VALUE_INPUTS, merged, provisional_values, quarter_start, risk_level

ACTION_TABLE = UserAction.__tablename__

# Silver attributes a use case state carries (besides the bookkeeping below).
SILVER_FIELDS = (
    "name", "description", "stage", "status", *GATE_DATE_FIELDS.values(), "comment", "date_start", "date_delivery",
    "efficiency_score_eur", "quality_score_eur", "risk_reduction_score_eur", "strategic_value_score_eur",
    "solution_complexity_score", "confidence_score", "delivery_score", "one_time_costs", "running_costs",
    "depreciation_years", "measured_benefits", "actual_costs",
    "owner_id", "lead_id", "value_type_id", "solution_type_id", *RISK_ANSWERS, *FORM2_FIELDS, "is_active",
)
# User-action fields copied onto the state when set (Name and business unit never change).
_COPIED = (
    "description", "owner_id", "lead_id", "value_type_id", "solution_type_id", "stage", "status", "comment",
    *GATE_DATE_FIELDS.values(), *RISK_ANSWERS, *FORM2_FIELDS, "measured_benefits",
)
# Form 2 fields counted for the "complete the details" to-do (lead and solution type included).
FORM2_PROGRESS_FIELDS = ("lead_id", "solution_type_id", *FORM2_FIELDS)


def table_exists(session: Session, table: str = ACTION_TABLE) -> bool:
    # Created by the input orchestration (its first task run); until then there is no input.
    return inspect(session.connection()).has_table(table)


def processed_action_ids():
    return select(BusinessTransaction.bronze_id).where(BusinessTransaction.bronze_table_name == ACTION_TABLE)


def unprocessed_actions(session: Session) -> list[UserAction]:
    if not table_exists(session):
        return []
    return list(session.scalars(
        select(UserAction).where(UserAction.id.not_in(processed_action_ids())).order_by(UserAction.id)
    ))


def create_records(session: Session, use_case_ids: list[int] | None = None) -> dict[int, UserAction]:
    """The create record of every use case created in the UI (through the
    BusinessTransaction of its first silver version)."""
    if not table_exists(session):
        return {}
    first = select(Initiative.use_case_id, func.min(Initiative.id).label("first_id")).group_by(Initiative.use_case_id)
    if use_case_ids is not None:
        first = first.where(Initiative.use_case_id.in_(use_case_ids))
    first = first.subquery()
    rows = session.execute(
        select(first.c.use_case_id, UserAction)
        .join(Initiative, Initiative.id == first.c.first_id)
        .join(BusinessTransaction, BusinessTransaction.id == Initiative.business_transaction_id)
        .join(UserAction, UserAction.id == BusinessTransaction.bronze_id)
        .where(BusinessTransaction.bronze_table_name == ACTION_TABLE)
    ).all()
    return {use_case_id: action for use_case_id, action in rows}


def first_stages(session: Session, use_case_ids: list[int] | None = None) -> dict[int, str]:
    """UseCaseID -> stage of its first silver version."""
    first = select(func.min(Initiative.id)).group_by(Initiative.use_case_id)
    if use_case_ids is not None:
        first = first.where(Initiative.use_case_id.in_(use_case_ids))
    return dict(session.execute(select(Initiative.use_case_id, Initiative.stage).where(Initiative.id.in_(first))).all())


def actions_of(session: Session, use_case_id: int, create: UserAction | None) -> list[UserAction]:
    """All user actions of a use case in order (processed or not)."""
    if not table_exists(session):
        return []
    condition = UserAction.use_case_id == use_case_id
    if create is not None:
        condition = condition | (UserAction.id == create.id)
    return list(session.scalars(select(UserAction).where(condition).order_by(UserAction.id)))


class Lookups:
    """Config rows by ID, loaded once per request."""

    def __init__(self, session: Session):
        self.owners = {o.id: o for o in session.scalars(select(Owner))}
        self.value_types = {t.id: t for t in session.scalars(select(ValueType))}
        self.solution_types = {t.id: t for t in session.scalars(select(SolutionType))}
        self.risks = {r.id: r for r in session.scalars(select(RiskClassification))}

    def business_unit(self, owner_id: int | None) -> str:
        owner = self.owners.get(owner_id)
        return (owner.category or "") if owner is not None else ""


def load_states(
    session: Session,
    use_case_ids: list[int] | None = None,
    include_pending_creates: bool = True,
    with_drivers: bool = False,
) -> list[dict]:
    """States of the given use cases (all when None), plus the use cases created
    in the UI and not processed yet (include_pending_creates)."""
    query = select(Initiative, AssessedInitiative).outerjoin(
        AssessedInitiative, AssessedInitiative.use_case_id == Initiative.use_case_id
    ).where(Initiative.id.in_(current_version_ids()))
    if use_case_ids is not None:
        query = query.where(Initiative.use_case_id.in_(use_case_ids))
    rows = session.execute(query.order_by(Initiative.use_case_id)).all()

    pending = unprocessed_actions(session)
    pending_by_use_case: dict[int, list[UserAction]] = defaultdict(list)
    for action in pending:
        if action.action_type != "create":
            pending_by_use_case[action.use_case_id].append(action)
    creates = create_records(session, use_case_ids)
    floors = first_stages(session, use_case_ids)

    states = []
    for version, gold in rows:
        state = _from_version(version, gold, creates.get(version.use_case_id))
        create = creates.get(version.use_case_id)
        # the stage given in form 1 (sheet use cases: the stage of their first version)
        state["stage_floor"] = (create.stage if create is not None and create.stage else None) or floors.get(version.use_case_id)
        on_top = pending_by_use_case.get(version.use_case_id, [])
        if on_top or with_drivers:
            all_actions = actions_of(session, version.use_case_id, creates.get(version.use_case_id))
            _overlay(state, on_top, all_actions)
            if with_drivers:
                state["drivers"] = merged(all_actions)
        _finish(state)
        states.append(state)

    if include_pending_creates and use_case_ids is None:
        for action in pending:
            if action.action_type == "create":
                states.append(pending_create_state(action, with_drivers))
    return states


def load_state(session: Session, id: int, with_drivers: bool = True) -> dict | None:
    """One use case by UseCaseID, or a pending create by −record ID."""
    if id < 0:
        if not table_exists(session):
            return None
        action = session.get(UserAction, -id)
        if action is None or action.action_type != "create":
            return None
        if session.scalar(processed_action_ids().where(BusinessTransaction.bronze_id == action.id)) is not None:
            return None  # processed: it is a use case now
        return pending_create_state(action, with_drivers)
    states = load_states(session, [id], include_pending_creates=False, with_drivers=with_drivers)
    return states[0] if states else None


def pending_create_state(action: UserAction, with_drivers: bool = False) -> dict:
    state = {name: None for name in SILVER_FIELDS}
    state.update(
        id=-action.id, use_case_id=None, version_id=None, user_action_id=action.id, gold=None,
        business_transaction_id=None,
        name=(action.name or "").strip(), is_active=True, status="pending",
        submitted_by=action.submitted_by, submitted_at=action.timestamp, changed_by=action.submitted_by,
        updated_at=action.timestamp, pending_action_ids=[action.id], last_action_id=action.id,
    )
    _overlay(state, [action], [action], copy_all=True)
    state["stage_floor"] = action.stage
    if with_drivers:
        state["drivers"] = merged([action])
    state["processing"] = "pending"
    _finish(state)
    return state


def _from_version(version: Initiative, gold: AssessedInitiative | None, create: UserAction | None) -> dict:
    state = {name: getattr(version, name) for name in SILVER_FIELDS}
    state.update(
        id=version.use_case_id, use_case_id=version.use_case_id, version_id=version.id, user_action_id=None,
        business_transaction_id=version.business_transaction_id,
        gold=gold, submitted_by=create.submitted_by if create else None,
        submitted_at=create.timestamp if create else None, changed_by=version.changed_by,
        updated_at=version.timestamp, pending_action_ids=[], last_action_id=None,
        processing="assessed" if gold is not None and gold.initiative_id == version.id else "not_assessed",
    )
    return state


def _overlay(state: dict, on_top: list[UserAction], all_actions: list[UserAction], copy_all: bool = False) -> None:
    """Lay unprocessed actions over the state, as the DAG will apply them."""
    for action in on_top:
        for name in _COPIED:
            value = getattr(action, name)
            if value is not None:
                state[name] = value
        for name in ("date_start", "date_delivery"):
            if getattr(action, name) is not None:
                state[name] = quarter_start(getattr(action, name))
        if action.solution_complexity_score is not None:
            state["solution_complexity_score"] = float(action.solution_complexity_score)
        if action.action_type == "approve":
            # approving passes the needs gate (the API sends the date; else it stays or is the approval time)
            state.update(status="approved", lead_id=action.lead_id,
                         needs_gate_date=action.needs_gate_date or state["needs_gate_date"] or action.timestamp)
        elif action.action_type == "reject":
            state["status"] = "rejected"
        state["changed_by"], state["updated_at"] = action.submitted_by, action.timestamp
        if not copy_all:
            state["pending_action_ids"].append(action.id)
            state["processing"] = "changes_pending"
    if on_top and any(getattr(a, n) is not None for a in on_top for n in VALUE_INPUTS):
        values = provisional_values(merged(all_actions))
        if values is not None:
            state.update(values)
    if on_top and any(a.actual_capex is not None or a.actual_opex is not None for a in on_top):
        actuals = merged(all_actions, ("actual_capex", "actual_opex"))
        state["actual_costs"] = float(sum(actuals.values()))
    if all_actions:
        state["last_action_id"] = max(a.id for a in all_actions)


def _finish(state: dict) -> None:
    gold = state.pop("gold", None)
    assessed = state["processing"] == "assessed"
    state["assessed_version_id"] = gold.initiative_id if gold is not None else None
    state["assessed_at"] = gold.assessed_at if gold is not None else None
    if assessed:
        state["potential_value_eur"] = gold.potential_value
        state["risk_level"] = gold.risk_classification_id
        state["provisional"] = False
    else:
        state["potential_value_eur"] = derived.provisional_potential(state)
        state["risk_level"] = risk_level(state)
        state["provisional"] = True
    state["realized_value_eur"] = gold.realized_value if assessed else None
    state["hypothetical_value_eur"] = derived.hypothetical_value(state)
    state["annual_cost_eur"] = derived.annual_cost(state)
    state["revision"] = f"{state['version_id'] or 0}-{state['last_action_id'] or 0}"
    day = today()
    state["last_gate"] = last_passed_gate(state, day)
    state["stage_problems"] = stage_problems(state["stage"], gate_dates(state), day)
    filled = sum(1 for name in FORM2_PROGRESS_FIELDS if state.get(name) not in (None, ""))
    state["form2_progress"] = {"filled": filled, "total": len(FORM2_PROGRESS_FIELDS)}


def with_refs(state: dict, lookups: Lookups) -> dict:
    """The state with owner, lead, value type, solution type and risk level as objects."""
    return {
        **state,
        "owner": lookups.owners.get(state["owner_id"]),
        "lead": lookups.owners.get(state["lead_id"]),
        "value_type": lookups.value_types.get(state["value_type_id"]),
        "solution_type": lookups.solution_types.get(state["solution_type_id"]),
        "risk_classification": (lookups.risks.get(state["risk_level"])
                                or ({"id": state["risk_level"], "name": str(state["risk_level"])}
                                    if state["risk_level"] else None)),
    }


# ---------- who may do what ----------


def user_owner_ids(lookups: Lookups, user) -> set[int]:
    """Owner rows that are the signed-in user: same e-mail, else same name (case-insensitive)."""
    email = (getattr(user, "email", None) or "").casefold()
    name = (getattr(user, "name", None) or "").casefold()
    return {
        o.id for o in lookups.owners.values()
        if (email and (o.email or "").casefold() == email) or (name and o.name.casefold() == name)
    }


def is_mine(state: dict, user, owner_ids: set[int]) -> bool:
    return (
        (state.get("submitted_by") is not None and state["submitted_by"] == user.name)
        or state.get("owner_id") in owner_ids
        or state.get("lead_id") in owner_ids
    )


def can_edit(state: dict, user, owner_ids: set[int], rights) -> bool:
    return bool(getattr(rights, "canAdmin", False)) or is_mine(state, user, owner_ids)


def can_decide(state: dict, rights) -> bool:
    return bool(getattr(rights, "canApprove", False)) and state["status"] == "pending" and state["id"] > 0


def todos(state: dict) -> list[str]:
    """Open tasks of the user for this use case."""
    result = []
    if state["status"] == "rejected":
        result.append("revise_and_resubmit")
    if state["status"] == "approved" and state["form2_progress"]["filled"] < state["form2_progress"]["total"]:
        result.append("complete_details")
    return result


def today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()
