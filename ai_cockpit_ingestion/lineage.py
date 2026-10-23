"""BusinessTransaction bookkeeping shared by RawToBronze and BronzeToSilver.

A transaction row is created with status "running" in its own short
database transaction, so it survives even if the work fails. The work then
sets it to "success" inside the data transaction (both commit or neither);
if that rolls back, mark_failed records the error separately.
"""
from __future__ import annotations

import datetime

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.models import KIND_RAW_TO_BRONZE, BusinessTransaction

STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def start_transaction(engine: Engine, **fields) -> int:
    with Session(engine) as session, session.begin():
        transaction = BusinessTransaction(status=STATUS_RUNNING, started_at=utcnow(), **fields)
        session.add(transaction)
        session.flush()
        return transaction.id


def mark_failed(engine: Engine, transaction_id: int, error: BaseException) -> None:
    with Session(engine) as session, session.begin():
        session.execute(
            update(BusinessTransaction)
            .where(BusinessTransaction.id == transaction_id)
            .values(status=STATUS_FAILED, finished_at=utcnow(), error=f"{type(error).__name__}: {error}"[:2000])
        )


def latest_bronze_load(session: Session, extract_table: str) -> BusinessTransaction | None:
    """The most recent successful RawToBronze load of an extract table."""
    return session.scalars(
        select(BusinessTransaction)
        .where(
            BusinessTransaction.kind == KIND_RAW_TO_BRONZE,
            BusinessTransaction.extract_table == extract_table,
            BusinessTransaction.status == STATUS_SUCCESS,
        )
        .order_by(BusinessTransaction.id.desc())
        .limit(1)
    ).first()
