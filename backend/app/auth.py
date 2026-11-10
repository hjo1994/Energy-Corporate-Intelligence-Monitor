"""Authentication/authorization via the internal eg-auth package.

Same integration form as the Digital Lab portal (and the platform template):
`authorizer()` is a FastAPI dependency (`Depends` instance) put on routers, and
`/api/auth/rights` tells the frontend what the signed-in user may do.

`eg-auth` is installed from the company mirror in the cluster; locally the stub
in `local_stubs/` stands in (EG_AUTH_DEV_MODE=True only, see its README).
"""
import os
from dataclasses import dataclass
from typing import Annotated, Any, List

from eg_auth import BaseRights, BooleanRightClaim
from eg_auth.fastapi import FastAPIResourceProtector, UserInfo
from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import demo_all_approvers  # TEMPORARY demo switch, see app/config.py

AUTH_TAG = "auth"


class Rights(BaseRights):
    canViewInitiatives: BooleanRightClaim
    canApprove: BooleanRightClaim  # approver inbox, decisions, re-use check
    canAdmin: BooleanRightClaim  # may edit every use case
    canManageUsers: BooleanRightClaim  # the Users page: grants and takes the approver role


def _groups(variable: str) -> set[str]:
    """AD groups from a comma-separated environment variable (empty: nobody)."""
    return {g.strip() for g in os.environ.get(variable, "").split(",") if g.strip()}


def map_groups_to_rights(ldap_groups: List[str]) -> Rights:
    # TODO: placeholder group copied from the platform template — replace with
    # the real group once the app has its own OIDC client. Today the API only
    # requires a signed-in user (`authorizer()` without a right); this right is
    # informational for the frontend until someone decides to gate on it.
    groups = set(ldap_groups)
    return Rights(
        canViewInitiatives="app_50hzt_aap_communities_all__x" in groups,
        # The approver and admin groups are set per installation (names still to come):
        # AI_COCKPIT_APPROVER_GROUPS, AI_COCKPIT_ADMIN_GROUPS. Admins may approve too.
        canApprove=bool(groups & (_groups("AI_COCKPIT_APPROVER_GROUPS") | _groups("AI_COCKPIT_ADMIN_GROUPS"))),
        canAdmin=bool(groups & _groups("AI_COCKPIT_ADMIN_GROUPS")),
        canManageUsers=False,  # set from canApprove in acting_user
    )


authorizer = FastAPIResourceProtector(groups_to_rights=map_groups_to_rights)

# ---------- demo presenters ----------
# For demos with one SSO account: the accounts in AI_COCKPIT_DEMO_PRESENTERS (comma-separated
# SSO display names, e-mail addresses or AD groups; empty = nobody, the default) switch their session
# between normal user and approver rights with the header "X-Demo-Role: approver" (see acting_user).
# The identity stays the SSO identity; what a presenter without the approver role does as demo
# approver is recorded under "<name> (demo approver)". Everyone else's header is ignored.
DEMO_ROLE_HEADER = "x-demo-role"
DEMO_APPROVER_SUFFIX = " (demo approver)"


def is_demo_presenter(user: Any) -> bool:
    allowed = {entry.casefold() for entry in _groups("AI_COCKPIT_DEMO_PRESENTERS")}
    if not allowed:
        return False
    email = (getattr(user, "email", None) or "").casefold()
    name = (getattr(user, "name", None) or "").strip().casefold()
    groups = {g.casefold() for g in (getattr(user, "groups", None) or [])}
    return bool((email and email in allowed) or (name and name in allowed) or groups & allowed)


@dataclass
class ActingUser:
    """The signed-in user as the API sees them: SSO identity, their AppUser row
    (app/users.py) and the rights from AD groups plus their role. A presenter
    switched to demo approver acts under "<name> (demo approver)"."""

    name: str
    email: str | None
    groups: List[str]
    rights: Rights
    sso_name: str = ""
    user_id: int | None = None
    role: str = "user"
    demo_presenter: bool = False
    demo_approver: bool = False


def _claims(rights: Any) -> dict:
    """The rights of an eg-auth UserInfo as a dict: the real package hands them over as a dict,
    the local stub (and older versions) as the Rights model."""
    if isinstance(rights, dict):
        return rights
    return rights.model_dump() if hasattr(rights, "model_dump") else dict(vars(rights))


def acting_user(request: Request, user: Annotated[UserInfo, authorizer()]) -> ActingUser:
    from app.users import is_listed_approver, sync_user

    with Session(request.app.state.write_engine) as session:
        record = sync_user(session, user)
        user_id, role = (record.id, record.role) if record is not None else (None, "user")
    if is_listed_approver(user):
        role = "approver"
    approver = role == "approver"
    claims = _claims(user.rights)
    can_approve = bool(claims.get("canApprove")) or approver
    # every real approver (role or AD group) manages the users; a demo approver does not
    rights = Rights(**{**{name: bool(claims.get(name)) for name in Rights.model_fields},
                       "canApprove": can_approve or demo_all_approvers(), "canManageUsers": can_approve})
    # A presenter's view follows the switch: "Approver (demo)" -> approver rights (recorded as
    # "<name> (demo approver)" unless they are an approver anyway), "Normal user" -> none, so
    # the normal user's view can be shown even by a real approver.
    presenter = is_demo_presenter(user)
    demo = presenter and request.headers.get(DEMO_ROLE_HEADER, "").strip().lower() == "approver"
    suffix = demo and not rights.canApprove
    if presenter:
        rights = rights.model_copy(update={"canApprove": demo})
    return ActingUser(
        name=f"{user.name}{DEMO_APPROVER_SUFFIX}" if suffix else user.name,
        email=getattr(user, "email", None), groups=list(getattr(user, "groups", None) or []), rights=rights,
        sso_name=user.name, user_id=user_id, role=role, demo_presenter=presenter, demo_approver=demo,
    )


CurrentUser = Annotated[ActingUser, Depends(acting_user)]

auth_router = APIRouter(prefix="/api", tags=[AUTH_TAG])


@auth_router.get("/auth/rights")
def get_user_rights(acting: CurrentUser, request: Request):
    from app.users import excel_owner_named, owner_of

    with Session(request.app.state.write_engine) as session:
        owner = owner_of(session, acting.user_id)
        if owner is None and acting.user_id is not None:
            try:
                owner = excel_owner_named(session, acting.sso_name)
            except OperationalError:
                owner = None
        owner_out = {"id": owner.id, "name": owner.name, "category": owner.category} if owner else None
    return {
        "user": acting.name,
        # what SSO delivered: the values AI_COCKPIT_APPROVERS and AI_COCKPIT_DEMO_PRESENTERS can name
        "email": acting.email,
        "groups": acting.groups,
        "rights": acting.rights,
        "role": acting.role,
        "user_id": acting.user_id,
        # the owner the user's use cases get; None: form 1 asks for the business unit
        "owner": owner_out,
        # may switch to demo approver (AI_COCKPIT_DEMO_PRESENTERS), and whether this request did
        "demo_presenter": acting.demo_presenter,
        "demo_approver": acting.demo_approver,
    }
