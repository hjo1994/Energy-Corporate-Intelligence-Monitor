"""SQLAlchemy models for the AI Cockpit data model.

Mirrors `solution documentation/Logical Data Model.drawio` in three groups,
matching the layers in `Architecture.drawio`:

- Bronze: one extract table per raw source sheet (IT_Initiatives_Extract,
  50Hertz_Initiatives_Extract, CorporateOneSAP_Initiatives_Extract,
  ETB_Initiatives_Extract). Append-only: every load adds its rows, nothing is
  updated or deleted. Every sheet column 1:1 and as text, plus the record ID
  _RecordId, the load's _BusinessTransactionId and the load columns
  _LoadTimestamp, _SourceFile and _SourceRow. Written by the RawToBronze DAG,
  generated from `sources.SOURCES`.
- Config: reference tables Owner, SolutionType, ValueType and
  RiskClassification.
- Silver: Initiative, upserted by the DAGs the BronzeToSilver meta DAG
  generates (one per extract table).
- BusinessTransaction: one row per RawToBronze load (per extract table) and
  per BronzeToSilver run. Bronze records and initiatives point to theirs, so
  every silver row can be traced back to the bronze load and source file.

The Backend service defines its own copy of the silver/config models —
Input Orchestration and Backend are separate deployments/images, so for
this prototype the schema is duplicated by hand rather than shared via a
common package. Keep both in sync.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table
from sqlalchemy.orm import declarative_base, relationship

from ai_cockpit_ingestion.sources import SOURCES

Base = declarative_base()

# --- Bronze -----------------------------------------------------------------

RECORD_ID_COLUMN = "_RecordId"
LOAD_COLUMNS = ("_BusinessTransactionId", "_LoadTimestamp", "_SourceFile", "_SourceRow")


def _extract_table(name: str, columns: tuple[str, ...]) -> Table:
    # Append-only: _RecordId identifies a record across all loads,
    # _BusinessTransactionId groups the records of one load.
    return Table(
        name,
        Base.metadata,
        Column(RECORD_ID_COLUMN, Integer, primary_key=True, autoincrement=True),
        *(Column(column, String, nullable=True) for column in columns),
        Column("_BusinessTransactionId", Integer, ForeignKey("business_transaction.id"), nullable=False),
        Column("_LoadTimestamp", DateTime, nullable=False),
        Column("_SourceFile", String, nullable=False),
        Column("_SourceRow", Integer, nullable=False),
    )


EXTRACT_TABLES: dict[str, Table] = {
    source.extract_table: _extract_table(source.extract_table, source.columns)
    for source in SOURCES
}

# --- Config -----------------------------------------------------------------


class Owner(Base):
    __tablename__ = "owner"

    id = Column(Integer, primary_key=True)
    # The source has no field literally named "Category". Confirmed mapping:
    # the originating business unit (IT / 50 Hertz / Corporate / ETB), which
    # is also exactly what the dashboard's "Business Unit" filter needs.
    category = Column(String, nullable=True)
    name = Column(String, nullable=False)
    department = Column(String, nullable=True)

    initiatives = relationship("Initiative", back_populates="owner")


class SolutionType(Base):
    """Reference/lookup table, seeded from the Variables sheet's "Solution
    Type" / "Solution Type description" columns (11 canonical categories).
    """

    __tablename__ = "solution_type"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)

    initiatives = relationship("Initiative", back_populates="solution_type")


class ValueType(Base):
    """Reference/lookup table, seeded from the Variables sheet's
    "Flagships/Pillars" / "Flagship description" columns.
    """

    __tablename__ = "value_type"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)

    initiatives = relationship("Initiative", back_populates="value_type")


class RiskClassification(Base):
    """The five levels of the risk pyramid in the Rahmenbetriebsvereinbarung
    KI (Abb. 1-3), seeded by the seed_config DAG — see transforms.risk_heuristic.
    The primary key is the level itself (1-5).
    """

    __tablename__ = "risk_classification"

    id = Column(Integer, primary_key=True, autoincrement=False)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    derived_action = Column(String, nullable=True)

    initiatives = relationship("Initiative", back_populates="risk_classification")


# --- Lineage ----------------------------------------------------------------


class BusinessTransaction(Base):
    """One RawToBronze load of an extract table or one BronzeToSilver run.

    Created with status "running" in its own short database transaction
    before the work starts, then set to "success" in the same transaction as
    the data it describes, or to "failed" if that transaction rolled back.
    """

    __tablename__ = "business_transaction"

    id = Column(Integer, primary_key=True)
    kind = Column(String, nullable=False)  # KIND_RAW_TO_BRONZE / KIND_BRONZE_TO_SILVER
    extract_table = Column(String, nullable=False)
    business_unit = Column(String, nullable=False)
    source_file = Column(String, nullable=True)
    load_timestamp = Column(DateTime, nullable=True)  # _LoadTimestamp of the bronze load written/read
    # BronzeToSilver: the RawToBronze transaction whose records were read.
    source_business_transaction_id = Column(Integer, ForeignKey("business_transaction.id"), nullable=True)
    status = Column(String, nullable=False)  # running / success / failed
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


KIND_RAW_TO_BRONZE = "raw_to_bronze"
KIND_BRONZE_TO_SILVER = "bronze_to_silver"


# --- Silver -----------------------------------------------------------------


class Initiative(Base):
    __tablename__ = "initiative"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    stage = Column(String, nullable=False)  # normalized Status, see transforms.normalize.normalize_stage

    # Only ETB has "Timing start"/"Timing delivery" (quarter labels, see
    # transforms.normalize.derive_timing_date); NULL for the other sources.
    date_start = Column(DateTime, nullable=True)
    date_delivery = Column(DateTime, nullable=True)

    # Value buckets in EUR per year (hypothetical value) — estimated by
    # transforms.value_heuristic; their sum is the hypothetical value.
    efficiency_score_eur = Column(Float, nullable=True)
    quality_score_eur = Column(Float, nullable=True)
    risk_reduction_score_eur = Column(Float, nullable=True)
    strategic_value_score_eur = Column(Float, nullable=True)

    solution_complexity_score = Column(Float, nullable=True)

    # Discount factors on the value buckets (0.35/0.60/0.80 and
    # 0.40/0.65/0.90): potential = sum(buckets) x confidence x delivery.
    confidence_score = Column(Float, nullable=True)
    delivery_score = Column(Float, nullable=True)

    one_time_costs = Column(Float, nullable=True)
    operating_costs = Column(Float, nullable=True)  # EUR per year
    depreciation_years = Column(Integer, nullable=True)

    owner_id = Column(Integer, ForeignKey("owner.id"), nullable=True)
    value_type_id = Column(Integer, ForeignKey("value_type.id"), nullable=True)
    solution_type_id = Column(Integer, ForeignKey("solution_type.id"), nullable=True)
    risk_classification_id = Column(Integer, ForeignKey("risk_classification.id"), nullable=False)

    # Upsert bookkeeping, see transforms.upsert_keys: key_hash decides
    # update vs. insert (the sources carry no initiative ID), row_hash whether
    # the source row changed at all.
    key_hash = Column(String(64), nullable=False, unique=True)
    row_hash = Column(String(64), nullable=False)
    # False once the initiative is no longer in its source sheet (soft delete).
    is_active = Column(Boolean, nullable=False, default=True)
    # The BronzeToSilver run that last inserted, changed or deactivated this row.
    business_transaction_id = Column(Integer, ForeignKey("business_transaction.id"), nullable=False)

    # When this silver row was last inserted, changed or deactivated.
    timestamp = Column(DateTime, nullable=False)

    owner = relationship("Owner", back_populates="initiatives")
    value_type = relationship("ValueType", back_populates="initiatives")
    solution_type = relationship("SolutionType", back_populates="initiatives")
    risk_classification = relationship("RiskClassification", back_populates="initiatives")
    business_transaction = relationship("BusinessTransaction")
