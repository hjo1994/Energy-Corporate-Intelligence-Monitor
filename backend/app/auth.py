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
from fastapi import APIRouter, Depends, HTTPException, Request

AUTH_TAG = "auth"


class Rights(BaseRights):
    canViewInitiatives: BooleanRightClaim
    canApprove: BooleanRightClaim  # approver inbox, decisions, re-use check
    canAdmin: BooleanRightClaim  # may edit every use case


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
    )


authorizer = FastAPIResourceProtector(groups_to_rights=map_groups_to_rights)

# ---------- demo presenters ----------
# For demos with one SSO account: the accounts in AI_COCKPIT_DEMO_PRESENTERS (comma-separated
# e-mail addresses or AD groups; empty = nobody, the default) may switch their session to
# admin rights with the header "X-Demo-Role: admin". The identity stays the SSO identity; what
# they do as demo admin is recorded under "<name> (demo admin)". Everyone else's header is ignored.
DEMO_ROLE_HEADER = "x-demo-role"
DEMO_ADMIN_SUFFIX = " (demo admin)"


def is_demo_presenter(user: Any) -> bool:
    allowed = {entry.casefold() for entry in _groups("AI_COCKPIT_DEMO_PRESENTERS")}
    if not allowed:
        return False
    email = (getattr(user, "email", None) or "").casefold()
    groups = {g.casefold() for g in (getattr(user, "groups", None) or [])}
    return bool((email and email in allowed) or groups & allowed)


@dataclass
class ActingUser:
    """The signed-in user as the API sees them (a presenter switched to demo admin)."""

    name: str
    email: str
    groups: List[str]
    rights: Rights


def acting_user(request: Request, user: Annotated[UserInfo, authorizer()]) -> UserInfo:
    if request.headers.get(DEMO_ROLE_HEADER, "").strip().lower() != "admin" or not is_demo_presenter(user):
        return user
    rights = user.rights.model_copy(update={"canApprove": True, "canAdmin": True})
    return ActingUser(  # type: ignore[return-value]
        name=f"{user.name}{DEMO_ADMIN_SUFFIX}", email=getattr(user, "email", ""),
        groups=list(getattr(user, "groups", None) or []), rights=rights,
    )


CurrentUser = Annotated[UserInfo, Depends(acting_user)]

auth_router = APIRouter(prefix="/api", tags=[AUTH_TAG])


def _role(rights: Rights) -> str:
    return "Admin" if rights.canAdmin else "Approver" if rights.canApprove else "Submitter"


@auth_router.get("/auth/dev-users", include_in_schema=False)
def get_dev_users():
    """Local demo only: the personas of the eg-auth stub (EG_AUTH_DEV_USERS) for the frontend's
    user switch. 404 unless EG_AUTH_DEV_MODE=True, so never in the cluster."""
    if os.getenv("EG_AUTH_DEV_MODE", "").lower() != "true":
        raise HTTPException(status_code=404)
    from eg_auth.fastapi import _AuthDevSettings  # the stub; only loaded in dev mode

    return [
        {"name": u["name"], "email": u["email"], "role": _role(map_groups_to_rights(list(u.get("groups", []))))}
        for u in _AuthDevSettings().dev_users
    ]


@auth_router.get("/auth/rights")
def get_user_rights(request: Request, user_info: Annotated[UserInfo, authorizer()]):
    acting = acting_user(request, user_info)
    return {
        "user": acting.name,
        "rights": acting.rights,
        # may switch to demo admin (AI_COCKPIT_DEMO_PRESENTERS), and whether this request did
        "demo_presenter": is_demo_presenter(user_info),
        "demo_admin": acting is not user_info,
    }
