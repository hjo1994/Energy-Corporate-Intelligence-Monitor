"""SQLAlchemy models for the AI Cockpit data model.

Mirrors `solution documentation/Logical Data Model.drawio` in three groups,
matching the layers in `Architecture.drawio`:

- Bronze: one extract table per raw source sheet (IT_Initiatives_Extract,
  50Hertz_Initiatives_Extract, CorporateOneSAP_Initiatives_Extract,
  ETB_Initiatives_Extract). Every sheet column 1:1 and as text, plus the load
  columns _LoadTimestamp, _SourceFile and _SourceRow. Written by the
  RawToBronze DAG, generated from `sources.SOURCES`.
- Config: reference tables Owner, SolutionType, ValueType and
  RiskClassification.
- Silver: Initiative, written by the DAGs the BronzeToSilver meta DAG
  generates (one per extract table).

The Backend service defines its own copy of the silver/config models —
Input Orchestration and Backend are separate deployments/images, so for
this prototype the schema is duplicated by hand rather than shared via a
common package. Keep both in sync.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Table
from sqlalchemy.orm import declarative_base, relationship

from ai_cockpit_ingestion.sources import SOURCES

Base = declarative_base()

# --- Bronze -----------------------------------------------------------------

LOAD_COLUMNS = ("_LoadTimestamp", "_SourceFile", "_SourceRow")


def _extract_table(name: str, columns: tuple[str, ...]) -> Table:
    # No surrogate key: the extract is replaced as a whole on every load, and
    # _SourceRow (the sheet's row number) already identifies a row.
    return Table(
        name,
        Base.metadata,
        *(Column(column, String, nullable=True) for column in columns),
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


# --- Silver -----------------------------------------------------------------


class Initiative(Base):
    __tablename__ = "initiative"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    stage = Column(String, nullable=False)  # normalized Status, see transforms.normalize.normalize_status

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

    # When this silver row was written.
    timestamp = Column(DateTime, nullable=False)

    owner = relationship("Owner", back_populates="initiatives")
    value_type = relationship("ValueType", back_populates="initiatives")
    solution_type = relationship("SolutionType", back_populates="initiatives")
    risk_classification = relationship("RiskClassification", back_populates="initiatives")
