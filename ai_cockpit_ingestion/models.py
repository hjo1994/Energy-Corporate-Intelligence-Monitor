"""SQLAlchemy models for the AI Cockpit data model.

Mirrors `solution documentation/Logical Data Model.drawio` in three groups,
matching the layers in `Architecture.drawio`:

- Bronze: one extract table per raw source sheet (IT_Initiatives_Extract,
  50Hertz_Initiatives_Extract, CorporateOneSAP_Initiatives_Extract,
  ETB_Initiatives_Extract). Append-only: every load adds its rows, nothing is
  updated or deleted. Every sheet column 1:1 and as text, plus ID (record
  key), Timestamp (one value per load) and SourceFileID. Written by the
  RawToBronze DAG, generated from `sources.SOURCES`.
- Config: reference tables Owner, SolutionType, ValueType and
  RiskClassification.
- Silver: Initiative, upserted by the DAGs the BronzeToSilver meta DAG
  generates (one per extract table).
- BusinessTransaction: one row per bronze record that BronzeToSilver turned
  into an inserted or changed initiative (BronzeTableName + BronzeID). The
  initiative points to it, so every silver row can be traced to its bronze
  record and from there to Timestamp and SourceFileID.

Table and column names in the database are exactly those of the data model
(PascalCase, e.g. Initiative.DateStart, OwnerID); the Python attributes stay
snake_case (Initiative.date_start). FK columns are named <Table>ID. IsActive
is not (yet) in the data model.

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

    initiatives = relationship("Initiative", back_populates="owner")


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

    initiatives = relationship("Initiative", back_populates="risk_classification")


# --- Lineage ----------------------------------------------------------------


class BusinessTransaction(Base):
    """One bronze record turned into an inserted or changed initiative.

    BronzeID is the ID of that record in the extract table named by
    BronzeTableName. It cannot be a database
    foreign key because it points into one of four tables.
    """

    __tablename__ = "BusinessTransaction"

    id = Column("ID", Integer, primary_key=True)
    bronze_id = Column("BronzeID", Integer, nullable=False)
    bronze_table_name = Column("BronzeTableName", String, nullable=False)


# --- Silver -----------------------------------------------------------------


class Initiative(Base):
    __tablename__ = "Initiative"

    id = Column("ID", Integer, primary_key=True)
    name = Column("Name", String, nullable=False)
    description = Column("Description", String, nullable=True)
    stage = Column("Stage", String, nullable=False)  # normalized Status, see transforms.normalize.normalize_stage

    # Only ETB has "Timing start"/"Timing delivery" (quarter labels, see
    # transforms.normalize.derive_timing_date); NULL for the other sources.
    date_start = Column("DateStart", DateTime, nullable=True)
    date_delivery = Column("DateDelivery", DateTime, nullable=True)

    # Value buckets in EUR per year (hypothetical value) — estimated by
    # transforms.value_heuristic; their sum is the hypothetical value.
    efficiency_score_eur = Column("EfficiencyScoreEur", Float, nullable=True)
    quality_score_eur = Column("QualityScoreEur", Float, nullable=True)
    risk_reduction_score_eur = Column("RiskReductionScoreEur", Float, nullable=True)
    strategic_value_score_eur = Column("StrategicValueScoreEur", Float, nullable=True)

    solution_complexity_score = Column("SolutionComplexityScore", Float, nullable=True)

    # Discount factors on the value buckets (0.35/0.60/0.80 and
    # 0.40/0.65/0.90): potential = sum(buckets) x confidence x delivery.
    confidence_score = Column("ConfidenceScore", Float, nullable=True)
    delivery_score = Column("DeliveryScore", Float, nullable=True)

    one_time_costs = Column("OneTimeCosts", Float, nullable=True)
    operating_costs = Column("OperatingCosts", Float, nullable=True)  # EUR per year
    depreciation_years = Column("DepreciationYears", Integer, nullable=True)

    owner_id = Column("OwnerID", Integer, ForeignKey("Owner.ID"), nullable=True)
    value_type_id = Column("ValueTypeID", Integer, ForeignKey("ValueType.ID"), nullable=True)
    solution_type_id = Column("SolutionTypeID", Integer, ForeignKey("SolutionType.ID"), nullable=True)
    risk_classification_id = Column("RiskClassificationID", Integer, ForeignKey("RiskClassification.ID"), nullable=False)

    # Upsert bookkeeping (KeyHash, RowHash in the data model), see
    # transforms.upsert_keys: key_hash decides update vs. insert (the sources
    # carry no initiative ID), row_hash whether the source row changed at all.
    key_hash = Column("KeyHash", String(64), nullable=False, unique=True)
    row_hash = Column("RowHash", String(64), nullable=False)
    # False once the initiative is no longer in its source sheet (soft delete).
    # Not (yet) in the data model.
    is_active = Column("IsActive", Boolean, nullable=False, default=True)
    # FK BusinessTransactionID: the bronze record this row was last built from.
    business_transaction_id = Column("BusinessTransactionID", Integer, ForeignKey("BusinessTransaction.ID"), nullable=False)

    # When this silver row was last inserted, changed or deactivated.
    timestamp = Column("Timestamp", DateTime, nullable=False)

    owner = relationship("Owner", back_populates="initiatives")
    value_type = relationship("ValueType", back_populates="initiatives")
    solution_type = relationship("SolutionType", back_populates="initiatives")
    risk_classification = relationship("RiskClassification", back_populates="initiatives")
    business_transaction = relationship("BusinessTransaction")
