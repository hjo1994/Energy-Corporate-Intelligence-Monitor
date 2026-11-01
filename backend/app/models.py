"""SQLAlchemy models for the AI Cockpit data model.

Hand-maintained copy of the input orchestration's `ai_cockpit_ingestion/models.py`
(separate deployments/images — no shared package at this prototype stage).
Table and column names in the database are exactly those of the data model
(PascalCase); the Python attributes and therefore the API fields stay
snake_case. The schema (incl. CHECK constraints and the migration) belongs
to the input orchestration; this copy only needs the columns the API reads or
writes. Keep both in sync.

Layers:
- Bronze UserActionExtracts (UserAction): one record per action in the UI —
  create (form 1), update (form 1 edits, form 2, stage gate), approve,
  reject. The only table the Backend writes.
- Silver Initiative: append-only, one row per version of a use case
  (UseCaseID); the current version is the one with the highest ID.
- Gold AssessedInitiatives (AssessedInitiative): one row per complete use
  case with PotentialValue, RealizedValue and the risk level.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, func, select
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Owner(Base):
    __tablename__ = "Owner"

    id = Column("ID", Integer, primary_key=True)
    category = Column("Category", String, nullable=True)  # business unit (source column "Source")
    name = Column("Name", String, nullable=False)
    department = Column("Department", String, nullable=True)
    email = Column("Email", String, nullable=True)  # to match the signed-in user


class SolutionType(Base):
    __tablename__ = "SolutionType"

    id = Column("ID", Integer, primary_key=True)
    name = Column("Name", String, nullable=False, unique=True)
    description = Column("Description", String, nullable=True)


class ValueType(Base):
    __tablename__ = "ValueType"

    id = Column("ID", Integer, primary_key=True)
    name = Column("Name", String, nullable=False, unique=True)
    description = Column("Description", String, nullable=True)


class RiskClassification(Base):
    """The five levels of the risk pyramid in the Rahmenbetriebsvereinbarung KI.
    The primary key is the level itself (1-5).
    """

    __tablename__ = "RiskClassification"

    id = Column("ID", Integer, primary_key=True, autoincrement=False)
    name = Column("Name", String, nullable=False, unique=True)
    description = Column("Description", String, nullable=True)
    derived_action = Column("DerivedAction", String, nullable=True)


class BusinessTransaction(Base):
    """Lineage written by the input orchestration: the bronze record
    (BronzeTableName + BronzeID) a silver version was built from; also one per
    processed user action."""

    __tablename__ = "BusinessTransaction"

    id = Column("ID", Integer, primary_key=True)
    bronze_id = Column("BronzeID", Integer, nullable=False)
    bronze_table_name = Column("BronzeTableName", String, nullable=False)


# Form 2 fields stored as plain values (same names in bronze, silver and gold).
FORM2_FIELDS = (
    "ai_layer", "enabling_team", "complexity_solidity", "strategic_kpis", "tactical_kpis", "value_domain",
    "autonomy_level", "eu_ai_act_class", "eu_ai_act_role", "works_council_risk_class", "target_user_groups",
    "applicable_to", "capability_direction", "safety_component", "works_council_approved_at", "expected_users",
)
RISK_ANSWERS = (
    "employee_personal_data", "performance_or_behaviour_control", "decisions_on_employees",
    "profiling_of_individuals", "changes_employee_workflows", "prohibited_practice",
)


class Initiative(Base):
    """Silver: one version of a use case (see the input orchestration's copy)."""

    __tablename__ = "Initiative"

    id = Column("ID", Integer, primary_key=True)  # version
    use_case_id = Column("UseCaseID", Integer, nullable=False)
    name = Column("Name", String, nullable=False)
    description = Column("Description", String, nullable=True)
    stage = Column("Stage", String, nullable=False)
    status = Column("Status", String, nullable=True)  # pending / approved / rejected; NULL = from a sheet
    stagegate = Column("Stagegate", String, nullable=True)  # last gate passed
    passed_at = Column("PassedAt", DateTime, nullable=True)
    comment = Column("Comment", String, nullable=True)  # comment of the last decision
    date_start = Column("DateStart", DateTime, nullable=True)
    date_delivery = Column("DateDelivery", DateTime, nullable=True)

    # Value buckets in EUR per year; their sum is the hypothetical value.
    efficiency_score_eur = Column("EfficiencyScoreEur", Float, nullable=True)
    quality_score_eur = Column("QualityScoreEur", Float, nullable=True)
    risk_reduction_score_eur = Column("RiskReductionScoreEur", Float, nullable=True)
    strategic_value_score_eur = Column("StrategicValueScoreEur", Float, nullable=True)
    solution_complexity_score = Column("SolutionComplexityScore", Float, nullable=True)
    confidence_score = Column("ConfidenceScore", Float, nullable=True)
    delivery_score = Column("DeliveryScore", Float, nullable=True)
    # Expected costs: estimated cost if delivered x DeliveryScore.
    one_time_costs = Column("OneTimeCosts", Float, nullable=True)
    running_costs = Column("RunningCosts", Float, nullable=True)  # EUR per year
    depreciation_years = Column("DepreciationYears", Integer, nullable=True)
    measured_benefits = Column("MeasuredBenefits", Float, nullable=True)
    actual_costs = Column("ActualCosts", Float, nullable=True)

    owner_id = Column("OwnerID", Integer, ForeignKey("Owner.ID"), nullable=True)
    lead_id = Column("LeadID", Integer, ForeignKey("Owner.ID"), nullable=True)
    value_type_id = Column("ValueTypeID", Integer, ForeignKey("ValueType.ID"), nullable=True)
    solution_type_id = Column("SolutionTypeID", Integer, ForeignKey("SolutionType.ID"), nullable=True)

    employee_personal_data = Column("EmployeePersonalData", String, nullable=True)
    performance_or_behaviour_control = Column("PerformanceOrBehaviourControl", Boolean, nullable=True)
    decisions_on_employees = Column("DecisionsOnEmployees", String, nullable=True)
    profiling_of_individuals = Column("ProfilingOfIndividuals", Boolean, nullable=True)
    changes_employee_workflows = Column("ChangesEmployeeWorkflows", Boolean, nullable=True)
    prohibited_practice = Column("ProhibitedPractice", Boolean, nullable=True)

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

    key_hash = Column("KeyHash", String(64), nullable=False)  # business unit + name, same in every version
    row_hash = Column("RowHash", String(64), nullable=False)
    is_active = Column("IsActive", Boolean, nullable=False, default=True)  # False = no longer in the source sheet
    business_transaction_id = Column("BusinessTransactionID", Integer, ForeignKey("BusinessTransaction.ID"), nullable=False)
    changed_by = Column("ChangedBy", String, nullable=True)
    timestamp = Column("Timestamp", DateTime, nullable=False)

    owner = relationship("Owner", foreign_keys=[owner_id])
    lead = relationship("Owner", foreign_keys=[lead_id])
    value_type = relationship("ValueType")
    solution_type = relationship("SolutionType")
    business_transaction = relationship("BusinessTransaction")


def current_version_ids():
    """SELECT of the ID of the current (newest) version of every use case."""
    return select(func.max(Initiative.id)).group_by(Initiative.use_case_id)


class AssessedInitiative(Base):
    """Gold: one row per assessed use case (built by the silver_to_gold DAG)."""

    __tablename__ = "AssessedInitiatives"

    id = Column("ID", Integer, primary_key=True)
    use_case_id = Column("UseCaseID", Integer, nullable=False, unique=True)
    initiative_id = Column("InitiativeID", Integer, ForeignKey("Initiative.ID"), nullable=False)  # version assessed
    potential_value = Column("PotentialValue", Float, nullable=True)
    realized_value = Column("RealizedValue", Float, nullable=True)
    risk_classification_id = Column("RiskClassificationID", Integer, ForeignKey("RiskClassification.ID"), nullable=True)
    assessed_at = Column("AssessedAt", DateTime, nullable=False)
    # Gold also copies the silver fields for the dashboard; the API reads those
    # from the silver version instead, so they are not mapped here.

    risk_classification = relationship("RiskClassification")


class UserAction(Base):
    """Bronze UserActionExtracts: one record per action in the UI, append-only.
    Only the fields that are set count (update); see the input orchestration's
    copy for the CHECK constraints, which the API validates beforehand
    (app/schemas.py)."""

    __tablename__ = "UserActionExtracts"

    id = Column("ID", Integer, primary_key=True, autoincrement=True)
    timestamp = Column("Timestamp", DateTime, nullable=False)
    source_file_id = Column("SourceFileID", String, nullable=False, default="user-input")
    submitted_by = Column("SubmittedBy", String, nullable=False)
    action_type = Column("ActionType", String, nullable=False)  # create / update / approve / reject
    use_case_id = Column("UseCaseID", Integer, nullable=True)  # empty for create
    status = Column("Status", String, nullable=True)
    stagegate = Column("Stagegate", String, nullable=True)
    passed_at = Column("PassedAt", DateTime, nullable=True)
    comment = Column("Comment", String, nullable=True)

    name = Column("Name", String, nullable=True)
    description = Column("Description", String, nullable=True)
    owner_id = Column("OwnerID", Integer, ForeignKey("Owner.ID"), nullable=True)
    lead_id = Column("LeadID", Integer, ForeignKey("Owner.ID"), nullable=True)
    value_type_id = Column("ValueTypeID", Integer, ForeignKey("ValueType.ID"), nullable=True)
    solution_type_id = Column("SolutionTypeID", Integer, ForeignKey("SolutionType.ID"), nullable=True)
    stage = Column("Stage", String, nullable=True)
    date_start = Column("DateStart", String, nullable=True)  # quarter, "Q2 2027"
    date_delivery = Column("DateDelivery", String, nullable=True)

    # value drivers per lever; shares are fractions 0-1, an incomplete lever counts as zero
    cases_per_year = Column("CasesPerYear", Float, nullable=True)
    hours_saved_per_case = Column("HoursSavedPerCase", Float, nullable=True)
    error_rate_before = Column("ErrorRateBefore", Float, nullable=True)
    errors_avoided = Column("ErrorsAvoided", Float, nullable=True)
    cost_per_error = Column("CostPerError", Float, nullable=True)
    risk_events_per_year = Column("RiskEventsPerYear", Float, nullable=True)
    events_avoided = Column("EventsAvoided", Float, nullable=True)
    cost_per_event = Column("CostPerEvent", Float, nullable=True)
    delay_events_per_year = Column("DelayEventsPerYear", Float, nullable=True)
    cost_of_delay_per_event = Column("CostOfDelayPerEvent", Float, nullable=True)
    lead_time_saved = Column("LeadTimeSaved", Float, nullable=True)
    estimate_basis = Column("EstimateBasis", String, nullable=True)
    delivery_likelihood = Column("DeliveryLikelihood", String, nullable=True)
    solution_complexity_score = Column("SolutionComplexityScore", Integer, nullable=True)
    one_time_costs = Column("OneTimeCosts", Float, nullable=True)
    operating_costs = Column("OperatingCosts", Float, nullable=True)  # EUR per year (silver: RunningCosts)

    employee_personal_data = Column("EmployeePersonalData", String, nullable=True)
    performance_or_behaviour_control = Column("PerformanceOrBehaviourControl", Boolean, nullable=True)
    decisions_on_employees = Column("DecisionsOnEmployees", String, nullable=True)
    profiling_of_individuals = Column("ProfilingOfIndividuals", Boolean, nullable=True)
    changes_employee_workflows = Column("ChangesEmployeeWorkflows", Boolean, nullable=True)
    prohibited_practice = Column("ProhibitedPractice", Boolean, nullable=True)

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
    measured_benefits = Column("MeasuredBenefits", Float, nullable=True)
    actual_capex = Column("ActualCapex", Float, nullable=True)
    actual_opex = Column("ActualOpex", Float, nullable=True)

    owner = relationship("Owner", foreign_keys=[owner_id])
    lead = relationship("Owner", foreign_keys=[lead_id])
    value_type = relationship("ValueType")
    solution_type = relationship("SolutionType")
