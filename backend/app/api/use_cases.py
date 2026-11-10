"""Use-case endpoints for forms 1 and 2, "My use cases" and the approver inbox.

Writes go to the bronze table UserActionExtracts (action update / approve /
reject); reads lay the actions the pipeline has not processed yet over the
current silver version and its gold assessment (app/use_cases.py), so a change
is visible at once. Paths take the UseCaseID; an idea that is still being
processed has a negative id and can be read and decided, not changed.
"""
from __future__ import annotations

import datetime
import re
from typing import Annotated

from eg_auth.fastapi import UserInfo
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.initiatives import as_datetimes, check_stage_gates, commit
from app.auth import CurrentUser, authorizer
from app.config import initiative_input_enabled
from app.db import get_session, get_write_session
from app.lifecycle import below_floor, gate_dates
from app.models import GATE_DATE_FIELDS, Owner, SolutionType, UserAction, ValueType
from app.schemas import (
    ApprovalItem,
    DecisionIn,
    MyUseCase,
    SimilarUseCase,
    UseCaseDetail,
    UseCasePatch,
)
from app.use_cases import (
    Lookups,
    can_decide,
    can_edit,
    load_state,
    load_states,
    table_exists,
    today,
    todos,
    user_owner_ids,
    with_refs,
)
from app.user_input import RUNNING_COST_RANGES, utcnow

# form 1 values fixed once the idea is submitted (open again while a rejected idea is revised)
SUBMITTED_ONLY = ("description", "one_time_costs", "running_cost_range")

router = APIRouter(prefix="/api", tags=["use cases"], dependencies=[authorizer()])

User = CurrentUser


def _detail(session: Session, state: dict, user: UserInfo) -> UseCaseDetail:
    lookups = Lookups(session)
    owner_ids = user_owner_ids(lookups, user)
    return UseCaseDetail.model_validate({
        **with_refs(state, lookups),
        "can_edit": can_edit(state, user, owner_ids, user.rights) and state["id"] > 0,
        "can_decide": can_decide(state, user.rights),
        "todos": todos(state),
    })


def _state_or_404(session: Session, use_case_id: int, with_drivers: bool = True) -> dict:
    state = load_state(session, use_case_id, with_drivers=with_drivers)
    if state is None:
        raise HTTPException(status_code=404, detail="Use case not found")
    return state


def _writable(session: Session) -> None:
    if not initiative_input_enabled():
        raise HTTPException(status_code=403, detail="Changing use cases is switched off on this installation.")
    if not table_exists(session):
        raise HTTPException(status_code=503, detail="Not available yet: the pipeline has not created its table.")


def _check_revision(state: dict, base_revision: str | None) -> None:
    if base_revision is not None and base_revision != state["revision"]:
        raise HTTPException(
            status_code=409,
            detail={"message": "The use case was changed in the meantime. Please reload it and apply your "
                               "change again.", "revision": state["revision"]},
        )


def _not_processing(state: dict) -> None:
    if state["id"] < 0:
        raise HTTPException(status_code=409, detail="The idea is still being processed. Please try again in a minute.")


# ---------- reading ----------


@router.get("/me/use-cases", response_model=list[MyUseCase])
def my_use_cases(session: Annotated[Session, Depends(get_session)], user: User) -> list[MyUseCase]:
    """Use cases the signed-in user submitted, owns or leads, newest change first, with to-dos."""
    lookups = Lookups(session)
    owner_ids = user_owner_ids(lookups, user)
    result = []
    for state in load_states(session):
        roles = [role for role, mine in (
            ("submitter", state["submitted_by"] is not None and state["submitted_by"] == user.name),
            ("owner", state["owner_id"] in owner_ids),
            ("lead", state["lead_id"] in owner_ids),
        ) if mine]
        if not roles:
            continue
        result.append(MyUseCase.model_validate({
            **with_refs(state, lookups), "approval_status": state["status"], "roles": roles,
            "todos": todos(state), "can_edit": state["id"] > 0,
        }))
    epoch = datetime.datetime.min
    return sorted(result, key=lambda u: (bool(u.todos), u.updated_at or epoch), reverse=True)


@router.get("/use-cases/{use_case_id}", response_model=UseCaseDetail)
def get_use_case(use_case_id: int, session: Annotated[Session, Depends(get_session)], user: User) -> UseCaseDetail:
    """All fields of forms 1 and 2, the gold values, the entered drivers and what the user may do."""
    return _detail(session, _state_or_404(session, use_case_id), user)


@router.get("/approvals", response_model=list[ApprovalItem])
def approvals(session: Annotated[Session, Depends(get_session)], user: User) -> list[ApprovalItem]:
    """Ideas waiting for a decision, oldest first (approvers only)."""
    if not getattr(user.rights, "canApprove", False):
        raise HTTPException(status_code=403, detail="Only approvers can see the approval inbox.")
    lookups = Lookups(session)
    items = [
        ApprovalItem.model_validate({**with_refs(s, lookups), "can_decide": can_decide(s, user.rights)})
        for s in load_states(session) if s["status"] == "pending" and s["is_active"]
    ]
    epoch = datetime.datetime.min
    return sorted(items, key=lambda i: (i.submitted_at or epoch, i.id))


_WORD = re.compile(r"[a-zA-ZäöüÄÖÜß0-9]{3,}")
_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "are", "via", "using", "based", "our", "all",
    "der", "die", "das", "und", "für", "mit", "von", "den", "dem", "des", "eine", "ein", "einer", "auf", "aus",
}


def _words(state: dict) -> set[str]:
    text = f"{state.get('name') or ''} {state.get('description') or ''}".lower()
    return {w for w in _WORD.findall(text) if w not in _STOPWORDS}


@router.get("/use-cases/{use_case_id}/similar", response_model=list[SimilarUseCase])
def similar(use_case_id: int, session: Annotated[Session, Depends(get_session)], user: User,
            limit: int = 5) -> list[SimilarUseCase]:
    """Re-use check: other active use cases with the most words in common
    (name + description, Jaccard), score at least 0.1."""
    if not getattr(user.rights, "canApprove", False):
        raise HTTPException(status_code=403, detail="Only approvers can run the re-use check.")
    target = _state_or_404(session, use_case_id, with_drivers=False)
    words = _words(target)
    lookups = Lookups(session)
    scored = []
    for other in load_states(session, include_pending_creates=False):
        if other["id"] == target["id"] or not other["is_active"] or not words:
            continue
        other_words = _words(other)
        union = words | other_words
        score = len(words & other_words) / len(union) if union else 0.0
        if score >= 0.1:
            scored.append(SimilarUseCase.model_validate({**with_refs(other, lookups), "score": round(score, 3)}))
    return sorted(scored, key=lambda s: (-s.score, s.id))[: max(1, min(limit, 20))]


# ---------- writing ----------


@router.patch("/use-cases/{use_case_id}", response_model=UseCaseDetail)
def update_use_case(
    use_case_id: int,
    body: UseCasePatch,
    user: User,
    session: Annotated[Session, Depends(get_write_session)],
) -> UseCaseDetail:
    """Save form 2, the stage or gate dates as an 'update' action, at any time. Description and
    cost estimates only while a rejected idea is revised; the stage never below the one given in
    form 1 (422). Only the fields sent count (null = not sent). When the stage or a gate date is sent, stage
    and gate dates together must fit (422 otherwise). 409 when the use case changed since
    `base_revision` or while the idea is still being processed."""
    _writable(session)
    state = _state_or_404(session, use_case_id)
    _not_processing(state)
    lookups = Lookups(session)
    if not can_edit(state, user, user_owner_ids(lookups, user), user.rights):
        raise HTTPException(status_code=403, detail="Only the submitter, owner or lead can change this use case.")
    _check_revision(state, body.base_revision)

    fields = {k: v for k, v in body.model_dump(exclude={"base_revision", "resubmit"}).items() if v is not None}
    if not fields and not body.resubmit:
        raise HTTPException(status_code=422, detail="Nothing to change")
    locked = [f for f in SUBMITTED_ONLY if f in fields]
    if locked and state["status"] != "rejected":
        raise HTTPException(status_code=422, detail=f"{', '.join(locked)} cannot be changed after the idea was "
                                                    "submitted (only while a rejected idea is revised).")
    if "stage" in fields and below_floor(fields["stage"], state.get("stage_floor")):
        raise HTTPException(status_code=422, detail=f"The stage cannot go below {state['stage_floor']}, the stage "
                                                    "given when the idea was submitted.")
    if "stage" in fields or any(f in fields for f in GATE_DATE_FIELDS.values()):
        # an edit of something else is never blocked by an old mismatch (e.g. from the sheet)
        dates = gate_dates({**state, **fields})
        check_stage_gates(fields.get("stage", state["stage"]), dates, today())
    if body.resubmit:
        if state["status"] != "rejected":
            raise HTTPException(status_code=409, detail="Only a rejected idea can be resubmitted.")
        fields["status"] = "pending"

    if "owner_id" in fields:
        owner = lookups.owners.get(fields["owner_id"])
        if owner is None:
            raise HTTPException(status_code=422, detail="Unknown owner")
        if state["owner_id"] is not None and (owner.category or "") != lookups.business_unit(state["owner_id"]):
            raise HTTPException(status_code=422, detail="The business unit cannot change: choose an owner from "
                                                        f"{lookups.business_unit(state['owner_id']) or 'the same unit'}.")
    for field, table, label in (("lead_id", Owner, "lead"), ("value_type_id", ValueType, "topic (value type)"),
                                ("solution_type_id", SolutionType, "solution type")):
        if field in fields and session.get(table, fields[field]) is None:
            raise HTTPException(status_code=422, detail=f"Unknown {label}")

    if "running_cost_range" in fields:
        fields["operating_costs"] = RUNNING_COST_RANGES[fields.pop("running_cost_range")][1]
    if "applicable_to" in fields:
        fields["applicable_to"] = ",".join(dict.fromkeys(fields["applicable_to"]))
    as_datetimes(fields, ("works_council_approved_at", *GATE_DATE_FIELDS.values()))

    commit(session, UserAction(
        **fields, action_type="update", use_case_id=state["use_case_id"], timestamp=utcnow(),
        source_file_id="user-input", submitted_by=user.name,
    ))
    return _detail(session, _state_or_404(session, use_case_id), user)


@router.post("/use-cases/{use_case_id}/decision", response_model=UseCaseDetail)
def decide(
    use_case_id: int,
    body: DecisionIn,
    user: User,
    session: Annotated[Session, Depends(get_write_session)],
) -> UseCaseDetail:
    """Approve (with use case lead; passes the needs gate) or reject (with a comment) a pending
    idea. Approvers only. Approving sets the needs gate date to today unless the submitter has
    already dated it in the past; never later than a later gate that is already passed.
    Works before the pipeline has processed the idea (negative id): the action then refers
    to it by −(ID of its create record), which the pipeline resolves."""
    _writable(session)
    if not getattr(user.rights, "canApprove", False):
        raise HTTPException(status_code=403, detail="Only approvers can decide on ideas.")
    state = _state_or_404(session, use_case_id)
    if state["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"The idea is not waiting for a decision (status: "
                                                    f"{state['status'] or 'imported from a sheet'}).")
    _check_revision(state, body.base_revision)

    now = utcnow()
    if body.decision == "approve":
        if session.get(Owner, body.lead_id) is None:
            raise HTTPException(status_code=422, detail="Unknown lead")
        record = UserAction(action_type="approve", lead_id=body.lead_id, comment=body.comment,
                            needs_gate_date=_needs_gate_on_approval(state, now.date()))
    else:
        record = UserAction(action_type="reject", comment=body.comment)
    record.use_case_id = state["use_case_id"] if state["use_case_id"] is not None else state["id"]
    record.timestamp = now
    record.source_file_id, record.submitted_by = "user-input", user.name
    commit(session, record)
    return _detail(session, _state_or_404(session, use_case_id), user)


def _needs_gate_on_approval(state: dict, day: datetime.date) -> datetime.datetime | None:
    """The needs gate date an approval sets; None keeps the one the submitter gave (in the past)."""
    dates = gate_dates(state)
    if dates["Needs"] is not None and dates["Needs"] <= day:
        return None
    later = [d for gate, d in dates.items() if gate != "Needs" and d is not None and d <= day]
    return datetime.datetime.combine(min([day, *later]), datetime.time())
