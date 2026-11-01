"""SQLAlchemy models for the AI Cockpit data model.

Mirrors `solution documentation/Logical Data Model.drawio` in these groups,
matching the layers in `Architecture.drawio`:

- Bronze: one extract table per raw source sheet (IT_Initiatives_Extract,
  50Hertz_Initiatives_Extract, CorporateOneSAP_Initiatives_Extract,
  ETB_Initiatives_Extract). Append-only: every load adds its rows, nothing is
  updated or deleted. Every sheet column 1:1 and as text, plus ID (record
  key), Timestamp (one value per load) and SourceFileID. Written by the
  RawToBronze DAG, generated from `sources.SOURCES`.
- Bronze, user actions: UserActionExtracts, one record per action in the UI
  (written by the Backend): create (form 1, a new AI idea), update (form 1
  edits, form 2, a stage gate), approve, reject. Append-only as well, but
  typed: config references are IDs, value drivers and costs are numbers, risk
  indicators are fixed answers, all checked by constraints.
- Config: reference tables Owner, SolutionType, ValueType and
  RiskClassification.
- Silver: Initiative, append-only and versioned: one row per version of a
  use case (UseCaseID), written by the DAGs the BronzeToSilver meta DAG
  generates (one per bronze table). The current version is the newest one.
- Gold: AssessedInitiatives, one row per use case with PotentialValue,
  RealizedValue and the risk level, built by SilverToGold from the current
  silver version.
- TransformationRun: technical log of the bronze_to_silver runs, one row per
  run and bronze table (when, up to which bronze Timestamp, outcome, counts).
  The DAGs' sensors read it to tell whether a table has new data.
- BusinessTransaction: one row per bronze record that BronzeToSilver turned
  into a silver version (BronzeTableName + BronzeID), and per processed user
  action. The version points to it, so every silver row can be traced to its
  bronze record and from there to Timestamp and SourceFileID.

Table and column names in the database are exactly those of the data model
(PascalCase, e.g. Initiative.DateStart, OwnerID); the Python attributes stay
snake_case (Initiative.date_start). FK columns are named <Table>ID. IsActive
is not (yet) in the data model.

The Backend service defines its own copy of the bronze user-action, silver, gold and config models —
Input Orchestration and Backend are separate deployments/images, so for
this prototype the schema is duplicated by hand rather than shared via a
common package. Keep both in sync.
"""
from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, String, Table, func, select
from sqlalchemy.orm import declarative_base, relationship

from ai_cockpit_ingestion.sources import SOURCES, USER_INPUT_SOURCE

Base = declarative_base()

# --- Bronze -----------------------------------------------------------------

# Names as in the Logical Data Model (the extract tables keep the sheet's own
# column names, so the technical columns are named literally there too).
RECORD_ID_COLUMN = "ID"
LOAD_COLUMNS = ("Timestamp", "SourceFileID")


def _extract_table(name: str, columns: tuple[str, ...]) -> Table:
    # Append-only: ID identifies a record across all loads (assigned in sheet
    # order), Timestamp groups the records of one load.
    return Table(
        name,
        Base.metadata,
        Column(RECORD_ID_COLUMN, Integer, primary_key=True, autoincrement=True),
        *(Column(column, String, nullable=True) for column in columns),
        Column("Timestamp", DateTime, nullable=False),
        # No SourceFile table in the data model: holds the source file's path.
        Column("SourceFileID", String, nullable=False),
    )


EXTRACT_TABLES: dict[str, Table] = {
    source.extract_table: _extract_table(source.extract_table, source.columns)
    for source in SOURCES
}

# --- Bronze: user actions -----------------------------------------------------

USER_ACTION_TABLE_NAME = USER_INPUT_SOURCE.extract_table  # "UserActionExtracts"
USER_INPUT_SOURCE_FILE_ID = "user-input"  # SourceFileID of every user-action record

# What a record does (written by the Backend, one record per action):
# - create:  form 1, a new AI idea; UseCaseID empty (BronzeToSilver assigns it), status pending
# - update:  form 1 edits, form 2, a stage gate date; only the fields that are set count
# - approve: needs gate passed; LeadID required
# - reject:  Comment required
ACTION_TYPES = ("create", "update", "approve", "reject")
APPROVAL_STATUSES = ("pending", "approved", "rejected")
STAGEGATES = ("Needs", "Scope", "Deploy", "Retire")

STAGES = ("Idea", "Exploration", "PoC", "MVP", "Implementation", "Production", "On hold", "Cancelled", "Unknown")
ESTIMATE_BASES = ("rough", "benchmark", "measured")  # how solid the value drivers are
DELIVERY_LIKELIHOODS = ("low", "medium", "high")
EMPLOYEE_PERSONAL_DATA = ("no", "pseudonymised", "yes")
DECISIONS_ON_EMPLOYEES = ("none", "prepares", "automated")

# Choice lists of form 1 and form 2 ("form 2 data fields", Business Analysis). Value domain
# (27 entries, list still to come) and autonomy level stay free text until the lists are final.
AI_LAYERS = (
    "AI for productivity and efficiency",
    "AI for business process optimization",
    "Operational and advanced AI",
)
ENABLING_TEAMS = ("DiY", "DiY with support from DWP", "ad-hoc IT support", "NEST", "EL.AI", "data science chapter", "other")
COMPLEXITY_SOLIDITIES = ESTIMATE_BASES  # rough guess / benchmark / measured
EU_AI_ACT_CLASSES = ("banned", "high-risk", "transparency", "minimal")
EU_AI_ACT_ROLES = ("provider", "deployer", "consumer")
WORKS_COUNCIL_RISK_CLASSES = ("hi", "med-de", "med", "med-lo", "lo")
CAPABILITY_DIRECTIONS = ("providing", "consuming")
APPLICABLE_TO = ("ETB", "50Hertz", "Windgrid", "EGI", "Group")  # several possible, stored comma-separated

# Value drivers in lever order (efficiency, quality, risk reduction, speed). Shares are
# fractions 0-1 (a percentage in the form is stored divided by 100), counts and EUR amounts
# are >= 0. A lever left empty counts as zero.
VALUE_DRIVERS = (
    "CasesPerYear", "HoursSavedPerCase",
    "ErrorRateBefore", "ErrorsAvoided", "CostPerError",
    "RiskEventsPerYear", "EventsAvoided", "CostPerEvent",
    "DelayEventsPerYear", "CostOfDelayPerEvent", "LeadTimeSaved",
)
_SHARES = ("ErrorRateBefore", "ErrorsAvoided", "EventsAvoided", "LeadTimeSaved")
_COUNTS_AND_AMOUNTS = tuple(c for c in VALUE_DRIVERS if c not in _SHARES)
RISK_ANSWERS = (
    "EmployeePersonalData", "PerformanceOrBehaviourControl", "DecisionsOnEmployees",
    "ProfilingOfIndividuals", "ChangesEmployeeWorkflows", "ProhibitedPractice",
)
_RISK_FLAGS = ("PerformanceOrBehaviourControl", "ProfilingOfIndividuals", "ChangesEmployeeWorkflows", "ProhibitedPractice")
_EUR_AMOUNTS = ("OneTimeCosts", "OperatingCosts", "MeasuredBenefits", "ActualCapex", "ActualOpex")

# Form 1 fields a create record must carry (the other actions may leave any of them empty).
CREATE_REQUIRED = (
    "Name", "Description", "OwnerID", "ValueTypeID", "Stage",
    "EstimateBasis", "DeliveryLikelihood", "SolutionComplexityScore", "OneTimeCosts", "OperatingCosts",
    *RISK_ANSWERS,
)

# Form 2 fields (plain values; LeadID, SolutionTypeID and the gate date are separate columns).
FORM2_TEXT_COLUMNS = (
    "AILayer", "EnablingTeam", "ComplexitySolidity", "StrategicKPIs", "TacticalKPIs", "ValueDomain",
    "AutonomyLevel", "EUAIActClass", "EUAIActRole", "WorksCouncilRiskClass", "TargetUserGroups",
    "ApplicableTo", "CapabilityDirection",
)


def _one_of(column: str, values: tuple[str, ...], prefix: str = "ck_useraction") -> CheckConstraint:
    listed = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return CheckConstraint(f'"{column}" IS NULL OR "{column}" IN ({listed})', name=f"{prefix}_{column.lower()}")


def _quarter(column: str) -> CheckConstraint:
    # "Q2 2027"; the form only offers quarters, like the source sheets
    return CheckConstraint(
        f'"{column}" IS NULL OR "{column}" GLOB \'Q[1-4] [0-9][0-9][0-9][0-9]\'',
        name=f"ck_useraction_{column.lower()}",
    )


def _all_set(columns: tuple[str, ...]) -> str:
    return " AND ".join(f'"{c}" IS NOT NULL' for c in columns)


USER_ACTION_TABLE = Table(
    USER_ACTION_TABLE_NAME,
    Base.metadata,
    Column(RECORD_ID_COLUMN, Integer, primary_key=True, autoincrement=True),
    Column("Timestamp", DateTime, nullable=False),
    Column("SourceFileID", String, nullable=False, default=USER_INPUT_SOURCE_FILE_ID),
    Column("SubmittedBy", String, nullable=False),
    # the action
    Column("ActionType", String, nullable=False),
    Column("UseCaseID", Integer, nullable=True),  # empty for create
    Column("Status", String, nullable=True),  # e.g. pending again after a resubmission
    Column("Stagegate", String, nullable=True),
    Column("PassedAt", DateTime, nullable=True),
    Column("Comment", String, nullable=True),
    # master data, config values by ID (Name and business unit cannot change after create)
    Column("Name", String, nullable=True),
    Column("Description", String, nullable=True),
    Column("OwnerID", Integer, ForeignKey("Owner.ID"), nullable=True),
    Column("LeadID", Integer, ForeignKey("Owner.ID"), nullable=True),
    Column("ValueTypeID", Integer, ForeignKey("ValueType.ID"), nullable=True),
    Column("SolutionTypeID", Integer, ForeignKey("SolutionType.ID"), nullable=True),  # form 2 since the AI layer
    Column("Stage", String, nullable=True),
    Column("DateStart", String, nullable=True),
    Column("DateDelivery", String, nullable=True),
    # value drivers
    *(Column(c, Float, nullable=True) for c in VALUE_DRIVERS),
    # delivery and cost
    Column("EstimateBasis", String, nullable=True),
    Column("DeliveryLikelihood", String, nullable=True),
    Column("SolutionComplexityScore", Integer, nullable=True),
    Column("OneTimeCosts", Float, nullable=True),
    Column("OperatingCosts", Float, nullable=True),  # EUR per year; form 1 sends a range's representative value
    # risk indicators (Rahmenbetriebsvereinbarung KI, Abb. 2)
    Column("EmployeePersonalData", String, nullable=True),
    Column("PerformanceOrBehaviourControl", Boolean, nullable=True),
    Column("DecisionsOnEmployees", String, nullable=True),
    Column("ProfilingOfIndividuals", Boolean, nullable=True),
    Column("ChangesEmployeeWorkflows", Boolean, nullable=True),
    Column("ProhibitedPractice", Boolean, nullable=True),
    # form 2
    *(Column(c, String, nullable=True) for c in FORM2_TEXT_COLUMNS),
    Column("SafetyComponent", Boolean, nullable=True),
    Column("WorksCouncilApprovedAt", DateTime, nullable=True),
    Column("ExpectedUsers", Integer, nullable=True),
    Column("MeasuredBenefits", Float, nullable=True),  # EUR, total to date
    Column("ActualCapex", Float, nullable=True),  # EUR, spent to date
    Column("ActualOpex", Float, nullable=True),  # EUR, spent to date
    _one_of("ActionType", ACTION_TYPES),
    _one_of("Status", APPROVAL_STATUSES),
    _one_of("Stagegate", STAGEGATES),
    CheckConstraint(f"\"ActionType\" <> 'create' OR ({_all_set(CREATE_REQUIRED)})", name="ck_useraction_create"),
    CheckConstraint('"ActionType" = \'create\' OR "UseCaseID" IS NOT NULL', name="ck_useraction_usecaseid"),
    CheckConstraint('"ActionType" <> \'approve\' OR "LeadID" IS NOT NULL', name="ck_useraction_approve"),
    CheckConstraint('"ActionType" <> \'reject\' OR "Comment" IS NOT NULL', name="ck_useraction_reject"),
    CheckConstraint('("Stagegate" IS NULL) = ("PassedAt" IS NULL)', name="ck_useraction_gate"),
    _one_of("Stage", STAGES),
    _quarter("DateStart"),
    _quarter("DateDelivery"),
    *(CheckConstraint(f'"{c}" IS NULL OR "{c}" >= 0', name=f"ck_useraction_{c.lower()}") for c in _COUNTS_AND_AMOUNTS),
    *(CheckConstraint(f'"{c}" IS NULL OR "{c}" BETWEEN 0 AND 1', name=f"ck_useraction_{c.lower()}") for c in _SHARES),
    _one_of("EstimateBasis", ESTIMATE_BASES),
    _one_of("DeliveryLikelihood", DELIVERY_LIKELIHOODS),
    CheckConstraint(
        '"SolutionComplexityScore" IS NULL OR "SolutionComplexityScore" BETWEEN 1 AND 9',
        name="ck_useraction_solutioncomplexityscore",
    ),
    *(CheckConstraint(f'"{c}" IS NULL OR "{c}" >= 0', name=f"ck_useraction_{c.lower()}") for c in _EUR_AMOUNTS),
    CheckConstraint('"ExpectedUsers" IS NULL OR "ExpectedUsers" >= 0', name="ck_useraction_expectedusers"),
    _one_of("EmployeePersonalData", EMPLOYEE_PERSONAL_DATA),
    _one_of("DecisionsOnEmployees", DECISIONS_ON_EMPLOYEES),
    *(CheckConstraint(f'"{c}" IS NULL OR "{c}" IN (0, 1)', name=f"ck_useraction_{c.lower()}") for c in (*_RISK_FLAGS, "SafetyComponent")),
    _one_of("AILayer", AI_LAYERS),
    _one_of("EnablingTeam", ENABLING_TEAMS),
    _one_of("ComplexitySolidity", COMPLEXITY_SOLIDITIES),
    _one_of("EUAIActClass", EU_AI_ACT_CLASSES),
    _one_of("EUAIActRole", EU_AI_ACT_ROLES),
    _one_of("WorksCouncilRiskClass", WORKS_COUNCIL_RISK_CLASSES),
    _one_of("CapabilityDirection", CAPABILITY_DIRECTIONS),
    Index("ix_useraction_timestamp", "Timestamp"),
    Index("ix_useraction_usecaseid", "UseCaseID"),
)

# --- Config -----------------------------------------------------------------


class Owner(Base):
    __tablename__ = "Owner"

    id = Column("ID", Integer, primary_key=True)
    # The source has no field literally named "Category". Confirmed mapping:
    # the originating business unit (IT / 50 Hertz / Corporate / ETB), which
    # is also exactly what the dashboard's "Business Unit" filter needs.
    category = Column("Category", String, nullable=True)
    name = Column("Name", String, nullable=False)
    department = Column("Department", String, nullable=True)

    initiatives = relationship("Initiative", back_populates="owner", foreign_keys="Initiative.owner_id")


class SolutionType(Base):
    """Reference/lookup table, seeded from the Variables sheet's "Solution
    Type" / "Solution Type description" columns (11 canonical categories).
    """

    __tablename__ = "SolutionType"

    id = Column("ID", Integer, primary_key=True)
    name = Column("Name", String, nullable=False, unique=True)
    description = Column("Description", String, nullable=True)

    initiatives = relationship("Initiative", back_populates="solution_type")


class ValueType(Base):
    """Reference/lookup table, seeded from the Variables sheet's
    "Flagships/Pillars" / "Flagship description" columns.
    """

    __tablename__ = "ValueType"

    id = Column("ID", Integer, primary_key=True)
    name = Column("Name", String, nullable=False, unique=True)
    description = Column("Description", String, nullable=True)

    initiatives = relationship("Initiative", back_populates="value_type")


class RiskClassification(Base):
    """The five levels of the risk pyramid in the Rahmenbetriebsvereinbarung
    KI (Abb. 1-3), seeded by the seed_config DAG — see transforms.risk_heuristic.
    The primary key is the level itself (1-5).
    """

    __tablename__ = "RiskClassification"

    id = Column("ID", Integer, primary_key=True, autoincrement=False)
    name = Column("Name", String, nullable=False, unique=True)
    description = Column("Description", String, nullable=True)
    derived_action = Column("DerivedAction", String, nullable=True)

    assessed_initiatives = relationship("AssessedInitiative", back_populates="risk_classification")


# --- Lineage ----------------------------------------------------------------


class BusinessTransaction(Base):
    """One bronze record turned into an inserted or changed initiative.

    BronzeID is the ID of that record in the extract table named by
    BronzeTableName. It cannot be a database
    foreign key because it points into one of several tables (the four
    extracts and UserActionExtracts).

    Every processed user-action record gets one, also when it changed nothing
    or was refused (unchanged, conflict), so it is read exactly once.
    """

    __tablename__ = "BusinessTransaction"

    id = Column("ID", Integer, primary_key=True)
    bronze_id = Column("BronzeID", Integer, nullable=False)
    bronze_table_name = Column("BronzeTableName", String, nullable=False)


class TransformationRun(Base):
    """One run of a bronze_to_silver DAG over its bronze table (technical/meta, no FKs).

    BronzeTimestamp is max(Timestamp) of the bronze table, taken BEFORE the run
    reads the data, so a record written during the run counts as new for the
    next one. A table has new data when its newest record is later than the
    newest BronzeTimestamp of a successful run (operators.new_bronze_sensor).
    Status: running -> success (in the same commit as the silver writes) or failed.
    """

    __tablename__ = "TransformationRun"
    __table_args__ = (
        CheckConstraint("\"Status\" IN ('running', 'success', 'failed')", name="ck_transformationrun_status"),
        Index("ix_transformationrun_table_status_bronzets", "BronzeTableName", "Status", "BronzeTimestamp"),
    )

    id = Column("ID", Integer, primary_key=True)
    bronze_table_name = Column("BronzeTableName", String, nullable=False)
    dag_run_id = Column("DagRunID", String, nullable=True)  # Airflow run_id, for tracing
    started_at = Column("StartedAt", DateTime, nullable=False)
    finished_at = Column("FinishedAt", DateTime, nullable=True)
    bronze_timestamp = Column("BronzeTimestamp", DateTime, nullable=True)  # NULL: table was empty
    status = Column("Status", String, nullable=False)
    rows_read = Column("RowsRead", Integer, nullable=True)
    rows_inserted = Column("RowsInserted", Integer, nullable=True)
    rows_updated = Column("RowsUpdated", Integer, nullable=True)
    rows_unchanged = Column("RowsUnchanged", Integer, nullable=True)
    rows_deactivated = Column("RowsDeactivated", Integer, nullable=True)
    rows_conflict = Column("RowsConflict", Integer, nullable=True)


# --- Silver -----------------------------------------------------------------


class Initiative(Base):
    """One version of a use case. Append-only: every change (sheet load, user
    action, soft delete) adds a new row with the same UseCaseID, nothing is
    updated in place. The current version of a use case is its row with the
    highest ID (see current_versions). Each version is a full snapshot.
    """

    __tablename__ = "Initiative"
    __table_args__ = (
        Index("ix_initiative_usecaseid", "UseCaseID"),
        Index("ix_initiative_keyhash", "KeyHash"),
    )

    id = Column("ID", Integer, primary_key=True)  # version
    # The use case across its versions; assigned by BronzeToSilver as max + 1.
    use_case_id = Column("UseCaseID", Integer, nullable=False)
    name = Column("Name", String, nullable=False)
    description = Column("Description", String, nullable=True)
    stage = Column("Stage", String, nullable=False)  # normalized Status, see transforms.normalize.normalize_stage

    # Approval workflow of the UI: pending -> approved / rejected. NULL for
    # initiatives imported from the sheets (already in the portfolio).
    status = Column("Status", String, nullable=True)
    # The last stage gate passed (Needs / Scope / Deploy / Retire) and when.
    stagegate = Column("Stagegate", String, nullable=True)
    passed_at = Column("PassedAt", DateTime, nullable=True)
    comment = Column("Comment", String, nullable=True)  # comment of the last decision

    # Only ETB and the UI have start/delivery quarters (see
    # transforms.normalize.derive_timing_date); NULL for the other sources.
    date_start = Column("DateStart", DateTime, nullable=True)
    date_delivery = Column("DateDelivery", DateTime, nullable=True)

    # Value buckets in EUR per year (hypothetical value) — estimated by
    # transforms.value_heuristic (sheets) or computed from the entered drivers
    # (transforms.user_input_heuristic); their sum is the hypothetical value.
    efficiency_score_eur = Column("EfficiencyScoreEur", Float, nullable=True)
    quality_score_eur = Column("QualityScoreEur", Float, nullable=True)
    risk_reduction_score_eur = Column("RiskReductionScoreEur", Float, nullable=True)
    strategic_value_score_eur = Column("StrategicValueScoreEur", Float, nullable=True)

    solution_complexity_score = Column("SolutionComplexityScore", Float, nullable=True)

    # Discount factors on the value buckets (0.35/0.60/0.80 and
    # 0.40/0.65/0.90): potential = sum(buckets) x confidence x delivery.
    confidence_score = Column("ConfidenceScore", Float, nullable=True)
    delivery_score = Column("DeliveryScore", Float, nullable=True)

    # Expected costs: estimated cost if delivered x DeliveryScore (since 24.10.2026).
    one_time_costs = Column("OneTimeCosts", Float, nullable=True)
    running_costs = Column("RunningCosts", Float, nullable=True)  # EUR per year
    depreciation_years = Column("DepreciationYears", Integer, nullable=True)

    # Real values reported in form 2 (EUR, to date); ActualCosts = capex + opex.
    measured_benefits = Column("MeasuredBenefits", Float, nullable=True)
    actual_costs = Column("ActualCosts", Float, nullable=True)

    owner_id = Column("OwnerID", Integer, ForeignKey("Owner.ID"), nullable=True)
    lead_id = Column("LeadID", Integer, ForeignKey("Owner.ID"), nullable=True)  # use case lead, set on approval
    value_type_id = Column("ValueTypeID", Integer, ForeignKey("ValueType.ID"), nullable=True)
    solution_type_id = Column("SolutionTypeID", Integer, ForeignKey("SolutionType.ID"), nullable=True)

    # The six risk answers (Rahmenbetriebsvereinbarung KI, Abb. 2); Gold derives
    # the risk level from them. Entered in the UI; for sheet initiatives the
    # canonical answers of the estimated level (transforms.risk_heuristic.risk_answers_for_level).
    employee_personal_data = Column("EmployeePersonalData", String, nullable=True)
    performance_or_behaviour_control = Column("PerformanceOrBehaviourControl", Boolean, nullable=True)
    decisions_on_employees = Column("DecisionsOnEmployees", String, nullable=True)
    profiling_of_individuals = Column("ProfilingOfIndividuals", Boolean, nullable=True)
    changes_employee_workflows = Column("ChangesEmployeeWorkflows", Boolean, nullable=True)
    prohibited_practice = Column("ProhibitedPractice", Boolean, nullable=True)

    # Form 2 (UI only)
    ai_layer = Column("AILayer", String, nullable=True)
    enabling_team = Column("EnablingTeam", String, nullable=True)
    complexity_solidity = Column("ComplexitySolidity", String, nullable=True)
    strategic_kpis = Column("StrategicKPIs", String, nullable=True)
    tactical_kpis = Column("TacticalKPIs", String, nullable=True)
    value_domain = Column("ValueDomain", String, nullable=True)
    autonomy_level = Column("AutonomyLevel", String, nullable=True)
    eu_ai_act_class = Column("EUAIActClass", String, nullable=True)
    eu_ai_act_role = Column("EUAIActRole", String, nullable=True)
    works_council_risk_class = Column("WorksCouncilRiskClass", String, nullable=True)
    target_user_groups = Column("TargetUserGroups", String, nullable=True)
    applicable_to = Column("ApplicableTo", String, nullable=True)
    capability_direction = Column("CapabilityDirection", String, nullable=True)
    safety_component = Column("SafetyComponent", Boolean, nullable=True)
    works_council_approved_at = Column("WorksCouncilApprovedAt", DateTime, nullable=True)
    expected_users = Column("ExpectedUsers", Integer, nullable=True)

    # Upsert bookkeeping (KeyHash, RowHash in the data model), see
    # transforms.upsert_keys: key_hash (business unit + name) finds the use
    # case of a sheet row; it is the same in every version of a use case, so
    # not unique here. row_hash tells whether anything changed: the source row's
    # hash for sheet versions, a hash of the version's content for UI versions.
    key_hash = Column("KeyHash", String(64), nullable=False)
    row_hash = Column("RowHash", String(64), nullable=False)
    # False once the initiative is no longer in its source sheet (soft delete:
    # a new version with IsActive = False). Not (yet) in the data model.
    is_active = Column("IsActive", Boolean, nullable=False, default=True)
    # FK BusinessTransactionID: the bronze record this version was built from.
    business_transaction_id = Column("BusinessTransactionID", Integer, ForeignKey("BusinessTransaction.ID"), nullable=False)
    changed_by = Column("ChangedBy", String, nullable=True)  # SubmittedBy of the user action; NULL for sheets

    # When this version was written.
    timestamp = Column("Timestamp", DateTime, nullable=False)

    owner = relationship("Owner", back_populates="initiatives", foreign_keys=[owner_id])
    lead = relationship("Owner", foreign_keys=[lead_id])
    value_type = relationship("ValueType", back_populates="initiatives")
    solution_type = relationship("SolutionType", back_populates="initiatives")
    business_transaction = relationship("BusinessTransaction")


# --- Gold -------------------------------------------------------------------


class AssessedInitiative(Base):
    """Gold: one row per use case, built by SilverToGold from the use case's
    current silver version once its value and risk inputs are complete.

    PotentialValue = sum(buckets) x confidence x delivery (EUR per year).
    RealizedValue = MeasuredBenefits - ActualCosts when real values were
    reported; otherwise, once DateDelivery has passed, the potential over the
    runtime minus the costs over the runtime; otherwise NULL. The risk level
    is derived from the six silver risk answers (deterministic rules).
    The rest is copied from silver so the dashboard reads one table.
    """

    __tablename__ = "AssessedInitiatives"

    id = Column("ID", Integer, primary_key=True)
    use_case_id = Column("UseCaseID", Integer, nullable=False, unique=True)
    initiative_id = Column("InitiativeID", Integer, ForeignKey("Initiative.ID"), nullable=False)  # silver version assessed
    potential_value = Column("PotentialValue", Float, nullable=True)
    realized_value = Column("RealizedValue", Float, nullable=True)
    risk_classification_id = Column("RiskClassificationID", Integer, ForeignKey("RiskClassification.ID"), nullable=True)
    assessed_at = Column("AssessedAt", DateTime, nullable=False)

    name = Column("Name", String, nullable=False)
    description = Column("Description", String, nullable=True)
    status = Column("Status", String, nullable=True)
    stagegate = Column("Stagegate", String, nullable=True)
    passed_at = Column("PassedAt", DateTime, nullable=True)
    stage = Column("Stage", String, nullable=False)
    date_start = Column("DateStart", DateTime, nullable=True)
    date_delivery = Column("DateDelivery", DateTime, nullable=True)
    owner_id = Column("OwnerID", Integer, ForeignKey("Owner.ID"), nullable=True)
    lead_id = Column("LeadID", Integer, ForeignKey("Owner.ID"), nullable=True)
    value_type_id = Column("ValueTypeID", Integer, ForeignKey("ValueType.ID"), nullable=True)
    solution_type_id = Column("SolutionTypeID", Integer, ForeignKey("SolutionType.ID"), nullable=True)
    ai_layer = Column("AILayer", String, nullable=True)
    enabling_team = Column("EnablingTeam", String, nullable=True)
    value_domain = Column("ValueDomain", String, nullable=True)
    capability_direction = Column("CapabilityDirection", String, nullable=True)
    applicable_to = Column("ApplicableTo", String, nullable=True)
    target_user_groups = Column("TargetUserGroups", String, nullable=True)
    expected_users = Column("ExpectedUsers", Integer, nullable=True)
    strategic_kpis = Column("StrategicKPIs", String, nullable=True)
    tactical_kpis = Column("TacticalKPIs", String, nullable=True)
    complexity_solidity = Column("ComplexitySolidity", String, nullable=True)
    autonomy_level = Column("AutonomyLevel", String, nullable=True)
    safety_component = Column("SafetyComponent", Boolean, nullable=True)
    eu_ai_act_class = Column("EUAIActClass", String, nullable=True)
    eu_ai_act_role = Column("EUAIActRole", String, nullable=True)
    works_council_risk_class = Column("WorksCouncilRiskClass", String, nullable=True)
    works_council_approved_at = Column("WorksCouncilApprovedAt", DateTime, nullable=True)
    is_active = Column("IsActive", Boolean, nullable=False, default=True)

    initiative = relationship("Initiative")
    risk_classification = relationship("RiskClassification", back_populates="assessed_initiatives")


# --- Silver versions (after all classes, since the mapper must be configured) ---

# Silver attributes that make up a version's content (everything except the
# version bookkeeping); compared to tell whether a recomputation changed anything.
VERSION_BOOKKEEPING = ("id", "use_case_id", "key_hash", "row_hash", "business_transaction_id", "changed_by", "timestamp")
VERSION_CONTENT = tuple(c.key for c in Initiative.__mapper__.column_attrs if c.key not in VERSION_BOOKKEEPING)


def current_versions():
    """SELECT of the current version (highest ID) of every use case."""
    latest = select(func.max(Initiative.id)).group_by(Initiative.use_case_id)
    return select(Initiative).where(Initiative.id.in_(latest))
