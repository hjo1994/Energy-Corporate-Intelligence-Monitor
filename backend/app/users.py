"""The signed-in users (AppUser) and their owners.

Every signed-in user gets a row in AppUser on their first request (sync_user):
e-mail (lowercase), SSO name and, when the token carries one, the SSO subject
as ExternalID. Role 'approver' gives the approver rights (inbox, decisions);
everyone else only sees and edits their own use cases. The accounts named in
AI_COCKPIT_APPROVERS (comma-separated e-mails or SSO names) are approvers
automatically, e.g. the very first one, who then grants the role to others on
the Users page.

A user becomes an Owner with their first use case (owner_for_create): their
own owner row (Owner.UserID), else the one Excel owner of the same name, which
gets linked, else a new owner with Source 'app' in the business unit they
choose in form 1.

The schema belongs to the input orchestration (its migration adds the table
and columns); ensure_user_schema does the same at Backend start-up, so the
API works even before the pipeline has migrated the shared database.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import AppUser, Owner

log = logging.getLogger(__name__)

_USER_COLUMNS = {
    "Owner": (
        ("UserID", 'INTEGER REFERENCES "AppUser" ("ID")'),
        ("Source", "VARCHAR NOT NULL DEFAULT 'excel' CHECK (\"Source\" IN ('excel', 'app'))"),
    ),
    "UserActionExtracts": (("SubmittedByUserID", 'INTEGER REFERENCES "AppUser" ("ID")'),),
    "Initiative": (
        ("CreatedByUserID", 'INTEGER REFERENCES "AppUser" ("ID")'),
        ("ChangedByUserID", 'INTEGER REFERENCES "AppUser" ("ID")'),
    ),
}


def ensure_user_schema(engine: Engine) -> None:
    """AppUser and the columns pointing to it, like the pipeline's migration (idempotent).
    A read-only database is left alone (logged)."""
    try:
        with engine.begin() as conn:
            conn.execute(text(
                'CREATE TABLE IF NOT EXISTS "AppUser" ("ID" INTEGER PRIMARY KEY, "Email" VARCHAR, '
                '"ExternalID" VARCHAR, "Name" VARCHAR NOT NULL, '
                "\"Role\" VARCHAR NOT NULL DEFAULT 'user', \"IsActive\" BOOLEAN NOT NULL DEFAULT 1, "
                "CONSTRAINT ck_appuser_role CHECK (\"Role\" IN ('user', 'approver')))"
            ))
            conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS "ux_appuser_email" ON "AppUser" ("Email")'))
            conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS "ux_appuser_externalid" ON "AppUser" ("ExternalID")'))
            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            for table, columns in _USER_COLUMNS.items():
                if table not in tables:
                    continue
                existing = {c["name"] for c in inspector.get_columns(table)}
                for name, definition in columns:
                    if name not in existing:
                        conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'))
                        log.info("Added %s.%s", table, name)
            if "Owner" in tables:
                conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS "ux_owner_userid" ON "Owner" ("UserID")'))
    except SQLAlchemyError as err:
        log.warning("Could not prepare the user table (%s); the pipeline's migration will add it", err)


def _listed(variable: str) -> set[str]:
    return {e.strip().casefold() for e in os.environ.get(variable, "").split(",") if e.strip()}


def _email(user: Any) -> str | None:
    email = (getattr(user, "email", None) or "").strip().lower()
    return email or None


def _external_id(user: Any) -> str | None:
    for attribute in ("oid", "sub", "user_id", "id"):
        value = getattr(user, attribute, None)
        if value:
            return str(value)
    return None


def is_listed_approver(user: Any) -> bool:
    """Named in AI_COCKPIT_APPROVERS by e-mail or SSO name."""
    allowed = _listed("AI_COCKPIT_APPROVERS")
    email = _email(user)
    name = (getattr(user, "name", None) or "").strip().casefold()
    return bool(allowed and ((email and email in allowed) or (name and name in allowed)))


def find_user(session: Session, user: Any) -> AppUser | None:
    external_id, email = _external_id(user), _email(user)
    if external_id:
        found = session.scalar(select(AppUser).where(AppUser.external_id == external_id))
        if found is not None:
            return found
    if email:
        found = session.scalar(select(AppUser).where(AppUser.email == email))
        if found is not None:
            return found
    name = (getattr(user, "name", None) or "").strip()
    if name:  # tokens without e-mail: the SSO name, unless that name belongs to someone with an e-mail
        return session.scalar(
            select(AppUser).where(func.lower(AppUser.name) == name.lower(), AppUser.email.is_(None)).limit(1)
        )
    return None


def sync_user(session: Session, user: Any) -> AppUser | None:
    """The AppUser row of the signed-in user, created on their first request.
    Keeps e-mail, ExternalID and name up to date and makes the accounts in
    AI_COCKPIT_APPROVERS approvers (never the other way round). None when the
    table is not there yet or the database is read-only."""
    try:
        record = find_user(session, user)
        name = (getattr(user, "name", None) or "").strip() or (_email(user) or "unknown")
        changed = False
        if record is None:
            record = AppUser(email=_email(user), external_id=_external_id(user), name=name, role="user",
                             is_active=True)
            session.add(record)
            changed = True
        else:
            for attribute, value in (("email", _email(user)), ("external_id", _external_id(user)), ("name", name)):
                if value and getattr(record, attribute) != value:
                    setattr(record, attribute, value)
                    changed = True
        if is_listed_approver(user) and record.role != "approver":
            record.role = "approver"
            changed = True
        if changed:
            session.commit()
        return record
    except SQLAlchemyError as err:
        session.rollback()
        if not isinstance(err, OperationalError):
            raise
        log.warning("User table not available: %s", err)
        return None


def owner_of(session: Session, user_id: int | None) -> Owner | None:
    if user_id is None:
        return None
    try:
        return session.scalar(select(Owner).where(Owner.user_id == user_id))
    except OperationalError:
        return None


def excel_owner_named(session: Session, name: str) -> Owner | None:
    """The one Excel owner of this name not yet linked to a user (none when the name is ambiguous)."""
    matches = session.scalars(
        select(Owner).where(func.lower(Owner.name) == name.strip().lower(), Owner.user_id.is_(None))
    ).all()
    return matches[0] if len(matches) == 1 else None


def owner_for_create(session: Session, user_id: int, name: str, business_unit: str | None) -> Owner | None:
    """The owner a new use case of this user gets (added to the session, not committed):
    their own, else the Excel owner of the same name (linked now), else a new one in
    `business_unit`. None when a new one is needed but no business unit was given."""
    owner = owner_of(session, user_id) or excel_owner_named(session, name)
    if owner is not None:
        owner.user_id = user_id
        return owner
    if not business_unit:
        return None
    owner = Owner(category=business_unit, name=name, department=None, user_id=user_id, source="app")
    session.add(owner)
    session.flush()
    return owner
