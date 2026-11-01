"""Stub of eg_auth.fastapi, hardened to the real integration form.

authorizer(...) must return a ``Depends`` instance — a naked function would make
FastAPI treat the parameter as user input and answer 422 (Fallenkatalog). The
stub only supports EG_AUTH_DEV_MODE=True; it cannot and must not fake a real
OIDC validation.
"""
from dataclasses import dataclass
from typing import Callable, List, Optional

from fastapi import Depends, HTTPException, Request
from pydantic_settings import BaseSettings, SettingsConfigDict

from eg_auth import BaseRights



class _AuthDevSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EG_AUTH_", extra="ignore")

    dev_mode: bool = False
    dev_groups: List[str] = []
    # the dev user's name, e-mail and groups, e.g. [{"name": "Jonas", "email": "jonas@demo.local",
    # "groups": []}]; with several entries (tests) "Authorization: Bearer dev:<email>" picks one
    dev_users: List[dict] = []


DEV_TOKEN_PREFIX = "dev:"


def dev_user(settings: _AuthDevSettings, authorization: Optional[str]) -> dict:
    """The persona the request asks for, else the first persona, else the single dev user."""
    email = ""
    if authorization and authorization.startswith("Bearer " + DEV_TOKEN_PREFIX):
        email = authorization[len("Bearer " + DEV_TOKEN_PREFIX):].strip().casefold()
    users = settings.dev_users
    for user in users:
        if email and str(user.get("email", "")).casefold() == email:
            return user
    if users:
        return users[0]
    return {"name": "Dev User", "email": "dev.user@example.com", "groups": settings.dev_groups}


@dataclass
class UserInfo:
    name: str
    email: str
    groups: List[str]
    rights: dict  # like the real package: the claims as a dict, not the Rights model


class FastAPIResourceProtector:
    def __init__(self, groups_to_rights: Callable[[List[str]], BaseRights]):
        self._groups_to_rights = groups_to_rights

    def __call__(self, **required_claims: bool):
        def dependency(request: Request) -> UserInfo:
            settings = _AuthDevSettings()
            if not settings.dev_mode:
                raise HTTPException(
                    status_code=401,
                    detail=(
                        "eg-auth stub: only EG_AUTH_DEV_MODE=True is supported locally. "
                        "Real OIDC validation requires the real eg-auth package."
                    ),
                )
            user = dev_user(settings, request.headers.get("authorization"))
            groups = list(user.get("groups", []))
            rights = self._groups_to_rights(groups)
            for claim, expected in required_claims.items():
                if getattr(rights, claim, None) != expected:
                    raise HTTPException(status_code=403, detail=f"Missing right: {claim}")
            return UserInfo(name=user["name"], email=user["email"], groups=groups, rights=rights.model_dump())

        return Depends(dependency)
