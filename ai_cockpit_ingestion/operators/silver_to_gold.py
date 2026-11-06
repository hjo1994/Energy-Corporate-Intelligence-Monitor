"""SilverToGold: assesses use cases from their current silver version into
AssessedInitiatives (one row per use case, updated in place; see
transforms.gold for the formulas).

A use case is due when its current version is complete (all value buckets,
ConfidenceScore and DeliveryScore, the six risk answers, OneTimeCosts and
RunningCosts set) and

- it has no gold row yet (it just became complete), or
- its current version is newer than the one its gold row was built from
  (a new version: one of the attributes the values depend on changed, or a
  descriptive field gold copies, such as status or stage gate), or
- its RealizedValue is runtime-based (DateDelivery passed, no measured
  benefits) and was last computed before today, since the runtime grows daily.

Incomplete use cases are left out of gold (the UI shows them from silver /
bronze, marked as not assessed yet). force=True assesses every complete use
case again. Every run is logged in TransformationRun with BronzeTableName
"Initiative" (the newest silver Timestamp as BronzeTimestamp).
"""
from __future__ import annotations

import datetime

from airflow.models.baseoperator import BaseOperator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.lineage import utcnow
from ai_cockpit_ingestion.models import AssessedInitiative, Initiative, TransformationRun, current_versions
from ai_cockpit_ingestion.transforms.gold import assess, is_complete, runtime_years

SILVER_TABLE_NAME = "Initiative"  # TransformationRun.BronzeTableName of the SilverToGold runs
_NOT_COPIED = ("id", "initiative_id", "potential_value", "realized_value", "risk_classification_id", "assessed_at")
# Gold columns copied 1:1 from the silver version (same attribute names).
COPIED = tuple(
    c.key for c in AssessedInitiative.__mapper__.column_attrs
    if c.key not in _NOT_COPIED and c.key in Initiative.__mapper__.column_attrs
)


def due_use_cases(session: Session, today: datetime.date, force: bool = False) -> list[Initiative]:
    """Current silver versions that need a (new) assessment, in UseCaseID order."""
    gold = {g.use_case_id: g for g in session.scalars(select(AssessedInitiative))}
    due = []
    for version in session.scalars(current_versions().order_by(Initiative.use_case_id)):
        if not is_complete(version):
            continue
        row = gold.get(version.use_case_id)
        if force or row is None or row.initiative_id != version.id or _runtime_stale(version, row, today):
            due.append(version)
    return due


def _runtime_stale(version: Initiative, row: AssessedInitiative, today: datetime.date) -> bool:
    runtime_based = version.measured_benefits is None and runtime_years(version.date_delivery, today) is not None
    return runtime_based and row.assessed_at.date() < today


def assess_into_gold(session: Session, force: bool, today: datetime.date | None = None) -> dict:
    today = today or utcnow().date()
    now = utcnow()
    counts = {"read": 0, "inserted": 0, "updated": 0, "unchanged": 0}
    gold = {g.use_case_id: g for g in session.scalars(select(AssessedInitiative))}
    due = due_use_cases(session, today, force)
    counts["read"] = len(due)
    for version in due:
        result = assess(version, today)
        values = {
            **{name: getattr(version, name) for name in COPIED},
            "initiative_id": version.id,
            "potential_value": result.potential_value,
            "realized_value": result.realized_value,
            "risk_classification_id": result.risk_level,
        }
        row = gold.get(version.use_case_id)
        if row is None:
            session.add(AssessedInitiative(**values, assessed_at=now))
            counts["inserted"] += 1
        elif all(_same(getattr(row, k), v) for k, v in values.items()):
            row.assessed_at = now  # checked today, nothing changed
            counts["unchanged"] += 1
        else:
            for name, value in values.items():
                setattr(row, name, value)
            row.assessed_at = now
            counts["updated"] += 1
    return counts


def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(a - b) < 1e-6
    return a == b


class SilverToGoldOperator(BaseOperator):
    template_fields = ("db_path",)

    def __init__(self, *, db_path: str, **kwargs):
        super().__init__(**kwargs)
        self.db_path = db_path

    def execute(self, context) -> dict:
        force = bool((context.get("params") or {}).get("force", False))
        dag_run = context.get("dag_run")
        engine = get_engine(self.db_path)
        try:
            with Session(engine) as session, session.begin():
                run = TransformationRun(
                    bronze_table_name=SILVER_TABLE_NAME, dag_run_id=dag_run.run_id if dag_run is not None else None,
                    started_at=utcnow(), bronze_timestamp=session.scalar(select(func.max(Initiative.timestamp))),
                    status="running",
                )
                session.add(run)
                session.flush()
                run_id = run.id
            try:
                with Session(engine) as session, session.begin():
                    counts = assess_into_gold(session, force)
                    run = session.get(TransformationRun, run_id)
                    run.status, run.finished_at, run.rows_read = "success", utcnow(), counts["read"]
                    run.rows_inserted, run.rows_updated, run.rows_unchanged = (
                        counts["inserted"], counts["updated"], counts["unchanged"])
            except Exception:
                with Session(engine) as session, session.begin():
                    run = session.get(TransformationRun, run_id)
                    run.status, run.finished_at = "failed", utcnow()
                raise
        finally:
            engine.dispose()
        self.log.info("Initiative -> AssessedInitiatives, force=%s: %s", force, counts)
        return counts
