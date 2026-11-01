"""Helpers for the versioned silver table (models.Initiative): use case IDs,
current versions, UI ownership and content comparison. Shared by the sheet
mode (operators.bronze_to_silver) and the user-action mode
(operators.user_input_to_silver).
"""
from __future__ import annotations

import datetime
import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.models import (
    USER_ACTION_TABLE_NAME,
    VERSION_CONTENT,
    BusinessTransaction,
    Initiative,
    current_versions,
)


class UseCaseIds:
    """Hands out new UseCaseIDs (max + 1) within one run; the run is a single
    transaction, and SQLite allows one writer at a time, so IDs never collide."""

    def __init__(self, session: Session):
        self._last = session.scalar(select(func.max(Initiative.use_case_id))) or 0

    def next(self) -> int:
        self._last += 1
        return self._last


def current_by_key(session: Session, keys) -> dict[str, Initiative]:
    """Current version per KeyHash (a KeyHash belongs to exactly one use case)."""
    keys = list(keys)
    if not keys:
        return {}
    return {i.key_hash: i for i in session.scalars(current_versions().where(Initiative.key_hash.in_(keys)))}


def current_version(session: Session, use_case_id: int) -> Initiative | None:
    return session.scalars(
        select(Initiative).where(Initiative.use_case_id == use_case_id).order_by(Initiative.id.desc()).limit(1)
    ).first()


def ui_owned_use_cases(session: Session) -> set[int]:
    """Use cases with at least one version built from a user action. The sheet
    import leaves them alone from then on (no update, no soft delete)."""
    ui_transactions = select(BusinessTransaction.id).where(
        BusinessTransaction.bronze_table_name == USER_ACTION_TABLE_NAME
    )
    return set(
        session.scalars(
            select(Initiative.use_case_id).where(Initiative.business_transaction_id.in_(ui_transactions)).distinct()
        )
    )


def content_of(version: Initiative) -> dict:
    return {name: getattr(version, name) for name in VERSION_CONTENT}


def _canonical(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(round(float(value), 6))
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    return str(value)


def content_hash(content: dict) -> str:
    """RowHash of a UI version: SHA-256 over its content, in VERSION_CONTENT order."""
    parts = [_canonical(content.get(name)) for name in VERSION_CONTENT]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def same_content(version: Initiative, content: dict) -> bool:
    current = content_of(version)
    return all(_canonical(current.get(name)) == _canonical(content.get(name)) for name in VERSION_CONTENT)
