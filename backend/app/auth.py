"""Authentication/authorization via the internal eg-auth package.

Same integration form as the Digital Lab portal (and the platform template):
`authorizer()` is a FastAPI dependency (`Depends` instance) put on routers, and
`/api/auth/rights` tells the frontend what the signed-in user may do.

`eg-auth` is installed from the company mirror in the cluster; locally the stub
in `local_stubs/` stands in (EG_AUTH_DEV_MODE=True only, see its README).
"""
import os
from typing import Annotated, List

from eg_auth import BaseRights, BooleanRightClaim
from eg_auth.fastapi import FastAPIResourceProtector, UserInfo
from fastapi import APIRouter

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

auth_router = APIRouter(prefix="/api", tags=[AUTH_TAG])


@auth_router.get("/auth/rights")
def get_user_rights(user_info: Annotated[UserInfo, authorizer()]):
    return {"user": user_info.name, "rights": user_info.rights}
