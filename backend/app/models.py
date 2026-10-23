"""SQLAlchemy models for the AI Cockpit data model.

Hand-maintained copy of `input-orchestration/ai_cockpit_ingestion/models.py`
(separate deployments/images — no shared package at this prototype stage).
Mirrors `solution documentation/Logical Data Model.drawio`, which only the
Fachbereich edits: keep this file in sync with the diagram and with the
input-orchestration copy, never the other way round.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Owner(Base):
    __tablename__ = "owner"

    id = Column(Integer, primary_key=True)
    category = Column(String, nullable=True)  # business unit (source column "Source")
    name = Column(String, nullable=False)
    department = Column(String, nullable=True)

    initiatives = relationship("Initiative", back_populates="owner")


class SolutionType(Base):
    __tablename__ = "solution_type"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)

    initiatives = relationship("Initiative", back_populates="solution_type")


class ValueType(Base):
    __tablename__ = "value_type"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)

    initiatives = relationship("Initiative", back_populates="value_type")


class RiskClassification(Base):
    """The five levels of the risk pyramid in the Rahmenbetriebsvereinbarung KI.
    The primary key is the level itself (1-5).
    """

    __tablename__ = "risk_classification"

    id = Column(Integer, primary_key=True, autoincrement=False)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    derived_action = Column(String, nullable=True)

    initiatives = relationship("Initiative", back_populates="risk_classification")


class BusinessTransaction(Base):
    """One RawToBronze load or BronzeToSilver run (lineage, written by the
    input orchestration). Only read here to trace an initiative to its source file."""

    __tablename__ = "business_transaction"

    id = Column(Integer, primary_key=True)
    kind = Column(String, nullable=False)
    extract_table = Column(String, nullable=False)
    business_unit = Column(String, nullable=False)
    source_file = Column(String, nullable=True)
    load_timestamp = Column(DateTime, nullable=True)
    source_business_transaction_id = Column(Integer, ForeignKey("business_transaction.id"), nullable=True)
    status = Column(String, nullable=False)
    force = Column(Boolean, nullable=False, default=False)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    rows_read = Column(Integer, nullable=True)
    inserted = Column(Integer, nullable=True)
    updated = Column(Integer, nullable=True)
    unchanged = Column(Integer, nullable=True)
    deactivated = Column(Integer, nullable=True)
    conflicts = Column(Integer, nullable=True)
    error = Column(String, nullable=True)


class Initiative(Base):
    __tablename__ = "initiative"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    stage = Column(String, nullable=False)

    date_start = Column(DateTime, nullable=True)
    date_delivery = Column(DateTime, nullable=True)

    # Value buckets in EUR per year, estimated by the input-orchestration value
    # heuristic; their sum is the hypothetical value.
    efficiency_score_eur = Column(Float, nullable=True)
    quality_score_eur = Column(Float, nullable=True)
    risk_reduction_score_eur = Column(Float, nullable=True)
    strategic_value_score_eur = Column(Float, nullable=True)

    solution_complexity_score = Column(Float, nullable=True)

    # Discount factors: potential = sum(buckets) x confidence x delivery.
    confidence_score = Column(Float, nullable=True)
    delivery_score = Column(Float, nullable=True)

    one_time_costs = Column(Float, nullable=True)
    operating_costs = Column(Float, nullable=True)  # EUR per year
    depreciation_years = Column(Integer, nullable=True)

    owner_id = Column(Integer, ForeignKey("owner.id"), nullable=True)
    value_type_id = Column(Integer, ForeignKey("value_type.id"), nullable=True)
    solution_type_id = Column(Integer, ForeignKey("solution_type.id"), nullable=True)
    risk_classification_id = Column(Integer, ForeignKey("risk_classification.id"), nullable=False)

    # Upsert bookkeeping of the input orchestration (see its transforms/upsert_keys.py).
    key_hash = Column(String(64), nullable=False, unique=True)
    row_hash = Column(String(64), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)  # False = no longer in the source sheet
    business_transaction_id = Column(Integer, ForeignKey("business_transaction.id"), nullable=False)

    timestamp = Column(DateTime, nullable=False)

    owner = relationship("Owner", back_populates="initiatives")
    value_type = relationship("ValueType", back_populates="initiatives")
    solution_type = relationship("SolutionType", back_populates="initiatives")
    risk_classification = relationship("RiskClassification", back_populates="initiatives")
    business_transaction = relationship("BusinessTransaction")
