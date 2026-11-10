"""BronzeToSilver for the UI (sources.USER_INPUT_SOURCE): applies the user
actions in UserActionExtracts to the versioned silver table.

Differences to the sheet mode (operators.bronze_to_silver):

- Incremental: only records without a BusinessTransaction yet are read, in
  ID order. Every record read gets one, whatever its outcome (new version,
  unchanged, conflict), so no record is applied twice and a stale update is
  never applied again later.
- No soft delete: a user action is not a snapshot.
- Each change is merged onto the use case's current version and written as a
  new version (full snapshot, same UseCaseID):
  - create: a new use case (UseCaseID = max + 1), status pending. KeyHash =
    business unit of the owner (Owner.Category) + name, like for the sheets.
    A key that already belongs to a use case is a conflict (the Backend
    rejects such input with 409); the record is not taken.
  - update: the fields that are set replace those of the current version.
    Name and business unit cannot change: a different name, or an owner from
    another business unit, is ignored (warning). Stage gate dates
    (NeedsGateDate ... RetireGateDate) are taken as given; the Backend checks
    them against the stage.
  - approve: only from pending -> approved, with the use case lead (LeadID);
    the Needs gate date becomes NeedsGateDate of the record, else the one the
    use case already has, else the record's Timestamp (the decision day).
  - reject: only from pending -> rejected, with the comment.
  - unknown use case, or a decision on a use case that is not pending ->
    conflict, nothing written.
  - UseCaseID < 0 refers to the use case created by create record −UseCaseID:
    the Backend lets an approver decide on (and record actions for) an idea
    before this DAG has given it its UseCaseID. Records run in ID order, so the
    create is always applied first.
  - the result equals the current version -> unchanged, nothing written.
- Value buckets, factors and costs come from the entered drivers
  (transforms.user_input_heuristic), merged over all actions of the use case
  in order (a later value wins), so an update may carry only the drivers that
  changed. They are recomputed whenever the merged actions contain the base
  inputs (EstimateBasis, DeliveryLikelihood, OneTimeCosts, OperatingCosts),
  which every create does; a sheet use case edited in the UI keeps its
  estimated buckets until those are entered. ActualCosts = ActualCapex +
  ActualOpex, merged the same way.
- RowHash of a UI version is the hash of its content (versions.content_hash).
- ChangedBy / ChangedByUserID of a version: SubmittedBy / SubmittedByUserID of
  its record; CreatedByUserID: SubmittedByUserID of the create record, kept in
  every later version (NULL for sheet use cases).
- The first user action on a sheet use case makes it UI-owned: the sheet
  import leaves it alone from then on.
- force=True additionally recomputes the current version of every use case
  that has user actions (e.g. after a formula change); a new version only
  where the result differs.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.lineage import utcnow
from ai_cockpit_ingestion.models import (
    USER_ACTION_TABLE,
    USER_ACTION_TABLE_NAME,
    GATE_DATE_COLUMNS,
    BusinessTransaction,
    Initiative,
    Owner,
)
from ai_cockpit_ingestion.transforms.gold import RISK_ANSWERS
from ai_cockpit_ingestion.transforms.normalize import clean_text
from ai_cockpit_ingestion.transforms.upsert_keys import key_hash, normalize
from ai_cockpit_ingestion.transforms.user_input_heuristic import estimate_user_input_value, quarter_start
from ai_cockpit_ingestion.versions import (
    UseCaseIds,
    content_hash,
    content_of,
    current_by_key,
    current_version,
    same_content,
    ui_owned_use_cases,
)

RISK_ANSWER_ATTRIBUTES = RISK_ANSWERS  # UI column -> silver attribute

# User-action columns copied 1:1 onto the version when they are set.
FIELD_ATTRIBUTES = {
    "Description": "description",
    "OwnerID": "owner_id",
    "LeadID": "lead_id",
    "ValueTypeID": "value_type_id",
    "SolutionTypeID": "solution_type_id",
    "Stage": "stage",
    "Status": "status",
    "Comment": "comment",
    **RISK_ANSWER_ATTRIBUTES,
    "AILayer": "ai_layer",
    "EnablingTeam": "enabling_team",
    "ComplexitySolidity": "complexity_solidity",
    "StrategicKPIs": "strategic_kpis",
    "TacticalKPIs": "tactical_kpis",
    "ValueDomain": "value_domain",
    "AutonomyLevel": "autonomy_level",
    "EUAIActClass": "eu_ai_act_class",
    "EUAIActRole": "eu_ai_act_role",
    "WorksCouncilRiskClass": "works_council_risk_class",
    "TargetUserGroups": "target_user_groups",
    "ApplicableTo": "applicable_to",
    "CapabilityDirection": "capability_direction",
    "SafetyComponent": "safety_component",
    "WorksCouncilApprovedAt": "works_council_approved_at",
    "ExpectedUsers": "expected_users",
    "MeasuredBenefits": "measured_benefits",
}
_TEXT_COLUMNS = ("Description", "Comment", "StrategicKPIs", "TacticalKPIs", "ValueDomain", "AutonomyLevel", "TargetUserGroups")
BASE_INPUTS = ("EstimateBasis", "DeliveryLikelihood", "OneTimeCosts", "OperatingCosts")


def apply_user_actions(session: Session, force: bool, log: logging.Logger) -> dict:
    counts = {"read": 0, "inserted": 0, "updated": 0, "unchanged": 0, "conflicts": 0}
    processed = select(BusinessTransaction.bronze_id).where(
        BusinessTransaction.bronze_table_name == USER_ACTION_TABLE_NAME
    )
    records = [
        dict(r._mapping)
        for r in session.execute(
            select(USER_ACTION_TABLE).where(USER_ACTION_TABLE.c.ID.not_in(processed)).order_by(USER_ACTION_TABLE.c.ID)
        )
    ]
    counts["read"] = len(records)
    if records:
        context = _Context(session, log)
        for record in records:
            transaction = BusinessTransaction(bronze_id=record["ID"], bronze_table_name=USER_ACTION_TABLE_NAME)
            session.add(transaction)
            counts[context.apply(record, transaction)] += 1
            session.flush()  # the next record may concern the same use case
    if force:
        context = _Context(session, log)
        for use_case_id in sorted(ui_owned_use_cases(session)):
            counts[context.recompute(use_case_id)] += 1
    return counts


class _Context:
    def __init__(self, session: Session, log: logging.Logger):
        self.session = session
        self.log = log
        self.now = utcnow()
        self.business_units = {o.id: o.category or "" for o in session.scalars(select(Owner))}
        self.use_case_ids = UseCaseIds(session)

    # --- one record -----------------------------------------------------------

    def apply(self, record: dict, transaction: BusinessTransaction) -> str:
        if record["ActionType"] == "create":
            return self._create(record, transaction)
        current = current_version(self.session, self._use_case_id(record["UseCaseID"]))
        if current is None:
            return self._conflict(record, f"use case {record['UseCaseID']} does not exist")
        if record["ActionType"] in ("approve", "reject") and current.status != "pending":
            return self._conflict(record, f"use case {current.use_case_id} is {current.status or 'not in review'}, not pending")

        content = self._merge(current, record, self._actions_of(current.use_case_id, up_to=record["ID"]))
        if record["ActionType"] == "approve":
            content.update(
                status="approved", lead_id=record["LeadID"],
                needs_gate_date=record.get("NeedsGateDate") or current.needs_gate_date or record["Timestamp"],
            )
        elif record["ActionType"] == "reject":
            content["status"] = "rejected"
        if same_content(current, content):
            return "unchanged"
        self._add_version(current.use_case_id, current.key_hash, content, transaction, record, current.created_by_user_id)
        return "updated"

    def _create(self, record: dict, transaction: BusinessTransaction) -> str:
        key = key_hash(self.business_units.get(record["OwnerID"], ""), record["Name"])
        existing = current_by_key(self.session, [key]).get(key)
        if existing is not None:
            return self._conflict(record, f"the name is already used by use case {existing.use_case_id} in this business unit")
        content = self._merge(None, record, [record])
        self._add_version(self.use_case_ids.next(), key, content, transaction, record, record.get("SubmittedByUserID"))
        return "inserted"

    def recompute(self, use_case_id: int) -> str:
        """force: recompute the current version from all actions of the use case."""
        current = current_version(self.session, use_case_id)
        content = self._merge(current, {}, self._actions_of(use_case_id))
        if same_content(current, content):
            return "unchanged"
        self.session.add(
            Initiative(
                **content, use_case_id=use_case_id, key_hash=current.key_hash, row_hash=content_hash(content),
                business_transaction_id=current.business_transaction_id, changed_by=current.changed_by,
                created_by_user_id=current.created_by_user_id, changed_by_user_id=current.changed_by_user_id,
                timestamp=self.now,
            )
        )
        return "updated"

    # --- helpers --------------------------------------------------------------

    def _use_case_id(self, use_case_id: int | None) -> int | None:
        """UseCaseID of a record; a negative one is −(ID of the create record) of the use case."""
        if use_case_id is None or use_case_id > 0:
            return use_case_id
        return self.session.scalar(
            select(Initiative.use_case_id)
            .join(BusinessTransaction, Initiative.business_transaction_id == BusinessTransaction.id)
            .where(BusinessTransaction.bronze_table_name == USER_ACTION_TABLE_NAME,
                   BusinessTransaction.bronze_id == -use_case_id)
            .limit(1)
        )

    def _conflict(self, record: dict, reason: str) -> str:
        self.log.error(
            "Conflict: %s record %d (use case %s) not taken — %s",
            record["ActionType"], record["ID"], record["UseCaseID"], reason,
        )
        return "conflicts"

    def _add_version(self, use_case_id, key, content, transaction, record, created_by_user_id) -> None:
        self.session.add(
            Initiative(
                **content, use_case_id=use_case_id, key_hash=key, row_hash=content_hash(content),
                business_transaction=transaction, changed_by=record["SubmittedBy"],
                created_by_user_id=created_by_user_id, changed_by_user_id=record.get("SubmittedByUserID"),
                timestamp=self.now,
            )
        )

    def _actions_of(self, use_case_id: int, up_to: int | None = None) -> list[dict]:
        """All user actions of a use case in order: its create record (found
        through the BusinessTransaction of its first version) and every record
        carrying its UseCaseID (or −ID of the create record, see _use_case_id),
        up to and including record `up_to`."""
        table = USER_ACTION_TABLE
        first_version = select(func.min(Initiative.id)).where(Initiative.use_case_id == use_case_id).scalar_subquery()
        create_record = (
            select(BusinessTransaction.bronze_id)
            .join(Initiative, Initiative.business_transaction_id == BusinessTransaction.id)
            .where(Initiative.id == first_version, BusinessTransaction.bronze_table_name == USER_ACTION_TABLE_NAME)
        )
        create_id = self.session.scalar(create_record)
        condition = table.c.UseCaseID == use_case_id
        if create_id is not None:
            condition = condition | (table.c.ID == create_id) | (table.c.UseCaseID == -create_id)
        query = select(table).where(condition)
        if up_to is not None:
            query = query.where(table.c.ID <= up_to)
        return [dict(r._mapping) for r in self.session.execute(query.order_by(table.c.ID))]

    def _merge(self, current: Initiative | None, record: dict, actions: list[dict]) -> dict:
        content = content_of(current) if current is not None else {}
        if current is None:
            content.update(name=clean_text(record["Name"]), status="pending")
        elif record.get("Name") and normalize(record["Name"]).casefold() != normalize(current.name).casefold():
            self.log.warning(
                "Record %d: the name of use case %d cannot change (%r) — ignored",
                record["ID"], current.use_case_id, record["Name"],
            )

        for column, attribute in FIELD_ATTRIBUTES.items():
            value = record.get(column)
            if value is None:
                continue
            if column == "OwnerID" and current is not None and current.owner_id is not None and (
                self.business_units.get(value, "") != self.business_units.get(current.owner_id, "")
            ):
                self.log.warning(
                    "Record %d: owner %d is in another business unit than use case %d — ignored",
                    record["ID"], value, current.use_case_id,
                )
                continue
            content[attribute] = clean_text(value) if column in _TEXT_COLUMNS else value
        for column in ("DateStart", "DateDelivery"):
            if record.get(column) is not None:
                content["date_start" if column == "DateStart" else "date_delivery"] = quarter_start(record[column])
        if record.get("SolutionComplexityScore") is not None:
            content["solution_complexity_score"] = float(record["SolutionComplexityScore"])
        for gate, column in GATE_DATE_COLUMNS.items():
            if record.get(column) is not None:
                content[f"{gate.lower()}_gate_date"] = record[column]

        merged = _merged(actions)
        if all(merged.get(c) is not None for c in BASE_INPUTS):
            value = estimate_user_input_value(merged)
            content.update(
                efficiency_score_eur=value.efficiency_eur,
                quality_score_eur=value.quality_eur,
                risk_reduction_score_eur=value.risk_reduction_eur,
                strategic_value_score_eur=value.strategic_eur,
                confidence_score=value.confidence_score,
                delivery_score=value.delivery_score,
                one_time_costs=value.one_time_costs,
                running_costs=value.operating_costs,
                depreciation_years=value.depreciation_years,
            )
        actuals = [merged[c] for c in ("ActualCapex", "ActualOpex") if merged.get(c) is not None]
        if actuals:
            content["actual_costs"] = float(sum(actuals))
        content["is_active"] = True
        return content


def _merged(actions: list[dict]) -> dict:
    """The actions' values in order, a later non-empty value wins."""
    merged: dict = {}
    for action in actions:
        merged.update({k: v for k, v in action.items() if v is not None})
    return merged
