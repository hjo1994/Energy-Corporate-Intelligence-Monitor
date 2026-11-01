"""The Users page: every signed-in user (AppUser) and their role.

Only for accounts with canManageUsers (approvers and the admin groups). The
accounts named in AI_COCKPIT_APPROVERS stay approvers whatever is set here.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.initiatives import commit
from app.auth import CurrentUser
from app.db import get_write_session
from app.models import AppUser, Owner
from app.schemas import AppUserOut, RoleIn

router = APIRouter(prefix="/api/users", tags=["users"])


def _may_manage(user) -> None:
    if not getattr(user.rights, "canManageUsers", False):
        raise HTTPException(status_code=403, detail="Only approvers can manage users.")


def _out(user: AppUser, owners: dict[int, Owner]) -> AppUserOut:
    owner = owners.get(user.id)
    return AppUserOut(id=user.id, name=user.name, email=user.email, role=user.role, is_active=user.is_active,
                      owner_id=owner.id if owner else None, business_unit=owner.category if owner else None)


def _owners(session: Session) -> dict[int, Owner]:
    return {o.user_id: o for o in session.scalars(select(Owner).where(Owner.user_id.is_not(None)))}


@router.get("", response_model=list[AppUserOut])
def list_users(user: CurrentUser, session: Annotated[Session, Depends(get_write_session)]) -> list[AppUserOut]:
    _may_manage(user)
    owners = _owners(session)
    return [_out(u, owners) for u in session.scalars(select(AppUser).order_by(AppUser.name, AppUser.id))]


@router.put("/{user_id}/role", response_model=AppUserOut)
def set_role(user_id: int, body: RoleIn, user: CurrentUser,
             session: Annotated[Session, Depends(get_write_session)]) -> AppUserOut:
    _may_manage(user)
    record = session.get(AppUser, user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown user")
    if record.id == user.user_id and body.role != "approver":
        raise HTTPException(status_code=422, detail="You cannot take the approver role from yourself.")
    record.role = body.role
    commit(session, record)
    return _out(record, _owners(session))
