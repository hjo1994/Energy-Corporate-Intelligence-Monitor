"""SQLAlchemy models for the AI Cockpit data model.

Hand-maintained copy of `input-orchestration/ai_cockpit_ingestion/models.py`
(separate deployments/images — no shared package at this prototype stage).
Table and column names in the database are exactly those of the data model
(PascalCase); the Python attributes and therefore the API fields stay
snake_case. Mirrors `solution documentation/Logical Data Model.drawio`, which only the
Fachbereich edits: keep this file in sync with the diagram and with the
input-orchestration copy, never the other way round.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Owner(Base):
    __tablename__ = "Owner"

    id = Column("ID", Integer, primary_key=True)
    category = Column("Category", String, nullable=True)  # business unit (source column "Source")
    name = Column("Name", String, nullable=False)
    department = Column("Department", String, nullable=True)

    initiatives = relationship("Initiative", back_populates="owner")


class SolutionType(Base):
    __tablename__ = "SolutionType"

    id = Column("ID", Integer, primary_key=True)
    name = Column("Name", String, nullable=False, unique=True)
    description = Column("Description", String, nullable=True)

    initiatives = relationship("Initiative", back_populates="solution_type")


class ValueType(Base):
    __tablename__ = "ValueType"

    id = Column("ID", Integer, primary_key=True)
    name = Column("Name", String, nullable=False, unique=True)
    description = Column("Description", String, nullable=True)

    initiatives = relationship("Initiative", back_populates="value_type")


class RiskClassification(Base):
    """The five levels of the risk pyramid in the Rahmenbetriebsvereinbarung KI.
    The primary key is the level itself (1-5).
    """

    __tablename__ = "RiskClassification"

    id = Column("ID", Integer, primary_key=True, autoincrement=False)
    name = Column("Name", String, nullable=False, unique=True)
    description = Column("Description", String, nullable=True)
    derived_action = Column("DerivedAction", String, nullable=True)

    initiatives = relationship("Initiative", back_populates="risk_classification")


class BusinessTransaction(Base):
    """Lineage written by the input orchestration: the bronze record
    (BronzeTableName + BronzeID) an initiative was last built from."""

    __tablename__ = "BusinessTransaction"

    id = Column("ID", Integer, primary_key=True)
    bronze_id = Column("BronzeID", Integer, nullable=False)
    bronze_table_name = Column("BronzeTableName", String, nullable=False)


class Initiative(Base):
    __tablename__ = "Initiative"

    id = Column("ID", Integer, primary_key=True)
    name = Column("Name", String, nullable=False)
    description = Column("Description", String, nullable=True)
    stage = Column("Stage", String, nullable=False)

    date_start = Column("DateStart", DateTime, nullable=True)
    date_delivery = Column("DateDelivery", DateTime, nullable=True)

    # Value buckets in EUR per year, estimated by the input-orchestration value
    # heuristic; their sum is the hypothetical value.
    efficiency_score_eur = Column("EfficiencyScoreEur", Float, nullable=True)
    quality_score_eur = Column("QualityScoreEur", Float, nullable=True)
    risk_reduction_score_eur = Column("RiskReductionScoreEur", Float, nullable=True)
    strategic_value_score_eur = Column("StrategicValueScoreEur", Float, nullable=True)

    solution_complexity_score = Column("SolutionComplexityScore", Float, nullable=True)

    # Discount factors: potential = sum(buckets) x confidence x delivery.
    confidence_score = Column("ConfidenceScore", Float, nullable=True)
    delivery_score = Column("DeliveryScore", Float, nullable=True)

    # Expected costs: estimated cost if delivered x DeliveryScore (value heuristic, since 24.10.2026).
    one_time_costs = Column("OneTimeCosts", Float, nullable=True)
    operating_costs = Column("OperatingCosts", Float, nullable=True)  # EUR per year
    depreciation_years = Column("DepreciationYears", Integer, nullable=True)

    owner_id = Column("OwnerID", Integer, ForeignKey("Owner.ID"), nullable=True)
    value_type_id = Column("ValueTypeID", Integer, ForeignKey("ValueType.ID"), nullable=True)
    solution_type_id = Column("SolutionTypeID", Integer, ForeignKey("SolutionType.ID"), nullable=True)
    risk_classification_id = Column("RiskClassificationID", Integer, ForeignKey("RiskClassification.ID"), nullable=False)

    # Upsert bookkeeping of the input orchestration (see its transforms/upsert_keys.py).
    key_hash = Column("KeyHash", String(64), nullable=False, unique=True)
    row_hash = Column("RowHash", String(64), nullable=False)
    is_active = Column("IsActive", Boolean, nullable=False, default=True)  # False = no longer in the source sheet
    business_transaction_id = Column("BusinessTransactionID", Integer, ForeignKey("BusinessTransaction.ID"), nullable=False)

    timestamp = Column("Timestamp", DateTime, nullable=False)

    owner = relationship("Owner", back_populates="initiatives")
    value_type = relationship("ValueType", back_populates="initiatives")
    solution_type = relationship("SolutionType", back_populates="initiatives")
    risk_classification = relationship("RiskClassification", back_populates="initiatives")
    business_transaction = relationship("BusinessTransaction")


class UserInputRecord(Base):
    """Bronze: one initiative submitted through the input form
    (UserInput_Initiatives_Extract), append-only. The only table the Backend
    writes (POST /api/initiatives); the input orchestration's
    bronze_to_silver_user_input DAG turns it into an Initiative. The database
    guards enums and ranges with CHECK constraints (see the input-orchestration
    copy); the API validates the same rules beforehand (app/schemas.py).
    """

    __tablename__ = "UserInput_Initiatives_Extract"

    id = Column("ID", Integer, primary_key=True, autoincrement=True)
    timestamp = Column("Timestamp", DateTime, nullable=False)
    source_file_id = Column("SourceFileID", String, nullable=False, default="user-input")
    submitted_by = Column("SubmittedBy", String, nullable=False)
    name = Column("Name", String, nullable=False)
    description = Column("Description", String, nullable=False)
    owner_id = Column("OwnerID", Integer, ForeignKey("Owner.ID"), nullable=False)
    value_type_id = Column("ValueTypeID", Integer, ForeignKey("ValueType.ID"), nullable=False)
    solution_type_id = Column("SolutionTypeID", Integer, ForeignKey("SolutionType.ID"), nullable=False)
    stage = Column("Stage", String, nullable=False)
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
    estimate_basis = Column("EstimateBasis", String, nullable=False)
    delivery_likelihood = Column("DeliveryLikelihood", String, nullable=False)
    solution_complexity_score = Column("SolutionComplexityScore", Integer, nullable=False)
    one_time_costs = Column("OneTimeCosts", Float, nullable=False)
    operating_costs = Column("OperatingCosts", Float, nullable=False)  # EUR per year
    # risk indicators (Rahmenbetriebsvereinbarung KI, Abb. 2)
    employee_personal_data = Column("EmployeePersonalData", String, nullable=False)
    performance_or_behaviour_control = Column("PerformanceOrBehaviourControl", Boolean, nullable=False)
    decisions_on_employees = Column("DecisionsOnEmployees", String, nullable=False)
    profiling_of_individuals = Column("ProfilingOfIndividuals", Boolean, nullable=False)
    changes_employee_workflows = Column("ChangesEmployeeWorkflows", Boolean, nullable=False)
    prohibited_practice = Column("ProhibitedPractice", Boolean, nullable=False)

    owner = relationship("Owner")
    value_type = relationship("ValueType")
    solution_type = relationship("SolutionType")
