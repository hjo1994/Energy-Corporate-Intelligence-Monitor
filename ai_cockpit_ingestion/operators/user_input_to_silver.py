"""BronzeToSilver for the input form (sources.USER_INPUT_SOURCE): turns
UserInput_Initiatives_Extract records into silver initiatives.

Differences to the sheet mode (operators.bronze_to_silver):

- Incremental: only records without a BusinessTransaction yet are read, and
  each of them is applied (force=True reads all of them again and recomputes
  their initiatives).
- No soft delete: a submission is not a snapshot, an initiative entered
  once stays until it is changed elsewhere.
- Business unit per record, from its owner (Owner.Category); KeyHash is
  built like for the sheets (business unit + name), so the same initiative
  cannot exist twice in one business unit. The Backend rejects such input
  (409); should one get here anyway, the record is skipped as a conflict
  and the existing initiative, e.g. one from a sheet, is left untouched.
- Value, costs and risk level come from the entered drivers and
  indicators (transforms.user_input_heuristic), not from free text.

Every inserted or updated initiative gets a BusinessTransaction pointing to
its record, exactly like the sheet mode.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.lineage import utcnow
from ai_cockpit_ingestion.models import USER_INPUT_TABLE, USER_INPUT_TABLE_NAME, BusinessTransaction, Initiative, Owner
from ai_cockpit_ingestion.transforms.upsert_keys import key_hash, row_hash
from ai_cockpit_ingestion.transforms.user_input_heuristic import (
    estimate_user_input_value,
    quarter_start,
    user_input_risk_level,
)

# Everything the user entered; the technical columns are no content.
HASH_COLUMNS = tuple(
    c.name for c in USER_INPUT_TABLE.columns if c.name not in ("ID", "Timestamp", "SourceFileID", "SubmittedBy")
)


def upsert_user_input(session: Session, force: bool, log: logging.Logger) -> dict:
    counts = {"read": 0, "inserted": 0, "updated": 0, "conflicts": 0}
    now = utcnow()
    processed = select(BusinessTransaction.bronze_id).where(
        BusinessTransaction.bronze_table_name == USER_INPUT_TABLE_NAME
    )
    query = select(USER_INPUT_TABLE).order_by(USER_INPUT_TABLE.c.ID)
    if not force:
        query = query.where(USER_INPUT_TABLE.c.ID.not_in(processed))
    records = [dict(r._mapping) for r in session.execute(query)]
    counts["read"] = len(records)
    if not records:
        return counts

    business_units = {o.id: o.category or "" for o in session.scalars(select(Owner))}
    user_input_transactions = set(session.scalars(processed.with_only_columns(BusinessTransaction.id)))

    for record in records:
        key = key_hash(business_units.get(record["OwnerID"], ""), record["Name"])
        digest = row_hash(record, HASH_COLUMNS)
        current = session.scalars(select(Initiative).where(Initiative.key_hash == key)).one_or_none()
        if current is not None and current.business_transaction_id not in user_input_transactions:
            counts["conflicts"] += 1
            log.error(
                "Conflict: user input %r (record %d) has the key of initiative %d from another source — "
                "not taken, the existing initiative is left unchanged", record["Name"], record["ID"], current.id,
            )
            continue
        transaction = BusinessTransaction(bronze_id=record["ID"], bronze_table_name=USER_INPUT_TABLE_NAME)
        fields = _silver_fields(record)
        if current is None:
            session.add(
                Initiative(
                    **fields, key_hash=key, row_hash=digest, is_active=True,
                    business_transaction=transaction, timestamp=now,
                )
            )
            counts["inserted"] += 1
        else:
            for name, value in fields.items():
                setattr(current, name, value)
            current.row_hash = digest
            current.is_active = True
            current.business_transaction = transaction
            current.timestamp = now
            counts["updated"] += 1
        session.flush()  # the next record may have the same key
        user_input_transactions.add(transaction.id)
    return counts


def _silver_fields(record: dict) -> dict:
    value = estimate_user_input_value(record)
    return dict(
        name=record["Name"].strip(),
        description=record["Description"].strip(),
        stage=record["Stage"],
        date_start=quarter_start(record["DateStart"]),
        date_delivery=quarter_start(record["DateDelivery"]),
        efficiency_score_eur=value.efficiency_eur,
        quality_score_eur=value.quality_eur,
        risk_reduction_score_eur=value.risk_reduction_eur,
        strategic_value_score_eur=value.strategic_eur,
        solution_complexity_score=float(record["SolutionComplexityScore"]),
        confidence_score=value.confidence_score,
        delivery_score=value.delivery_score,
        one_time_costs=value.one_time_costs,
        operating_costs=value.operating_costs,
        depreciation_years=value.depreciation_years,
        owner_id=record["OwnerID"],
        value_type_id=record["ValueTypeID"],
        solution_type_id=record["SolutionTypeID"],
        risk_classification_id=user_input_risk_level(record).level,
    )
