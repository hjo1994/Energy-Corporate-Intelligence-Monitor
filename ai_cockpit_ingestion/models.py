"""SQLAlchemy models for the AI Cockpit data model.

Mirrors `solution documentation/Logical Data Model.drawio` (entities
Initiative, Owner, SolutionType, ValueType). The Backend service defines its
own copy of these models — Input Orchestration and Backend are separate
deployments/images, so for this prototype the schema is duplicated by hand
rather than shared via a common package. Keep both in sync; revisit as a
shared package if the duplication becomes a real maintenance problem.

SolutionType/ValueType are reference/lookup tables (name + description),
seeded from the source workbook's own "Variables" sheet — not derived from
individual initiative rows. ValueScore and SolutionComplexityScore are
properties of the individual Initiative (confirmed), not of the type it
references.

Fields from the source Excel that have no corresponding column here
(Impediments, High-Level Cost Assessment, Expected Outcome, Added Value,
Strategic Link, Strategic Link ETB, "2026") are intentionally not persisted
— see repo root README, "Bekannte Lücke Datenmodell <-> Quell-Excel".
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Owner(Base):
    __tablename__ = "owner"

    id = Column(Integer, primary_key=True)
    # The source Excel has no field literally named "Category". Confirmed
    # mapping: the sheet's "Source" column (the originating business unit —
    # IT / 50Hertz / Corporate & OneSAP+ / ETB), which is also exactly what
    # the dashboard's "Business Unit" filter needs.
    category = Column(String, nullable=True)
    name = Column(String, nullable=False)
    department = Column(String, nullable=True)

    initiatives = relationship("Initiative", back_populates="owner")


class SolutionType(Base):
    """Reference/lookup table, seeded from the Variables sheet's "Solution
    Type" / "Solution Type description" columns (11 canonical categories) —
    not from individual initiative rows.
    """

    __tablename__ = "solution_type"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)

    initiatives = relationship("Initiative", back_populates="solution_type")


class ValueType(Base):
    """Reference/lookup table, seeded from the Variables sheet's
    "Flagships/Pillars" / "Flagship description" columns — not from
    individual initiative rows.
    """

    __tablename__ = "value_type"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)

    initiatives = relationship("Initiative", back_populates="value_type")


class Initiative(Base):
    __tablename__ = "initiative"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, nullable=False)  # normalized, see transforms.normalize.normalize_status

    # "Timing start"/"Timing delivery" in the source are quarter labels
    # ("Q1".."Q4"), almost never a real date, and once a bare year with no
    # quarter at all — see transforms.normalize.derive_timing_date for the
    # (flagged, best-effort) heuristic used to turn those into dates.
    date_start = Column(DateTime, nullable=True)
    date_delivery = Column(DateTime, nullable=True)

    # Confirmed: these scores belong to the individual initiative, not to
    # the type it references. Normalized 1-10 scale either way:
    # - value_score: 50Hertz/IT/Corporate use the "Value" T-shirt size,
    #   ETB a direct 1-10 number; NULL for IT/Corporate & OneSAP+, which
    #   don't track a value score in the source at all (never fabricated).
    # - solution_complexity_score: 50Hertz/IT/Corporate use the "Solution
    #   Feasibility" T-shirt size, ETB a direct 1-10 "Complexity" number.
    value_score = Column(Float, nullable=True)
    solution_complexity_score = Column(Float, nullable=True)

    owner_id = Column(Integer, ForeignKey("owner.id"), nullable=True)
    value_type_id = Column(Integer, ForeignKey("value_type.id"), nullable=True)
    solution_type_id = Column(Integer, ForeignKey("solution_type.id"), nullable=True)

    owner = relationship("Owner", back_populates="initiatives")
    value_type = relationship("ValueType", back_populates="initiatives")
    solution_type = relationship("SolutionType", back_populates="initiatives")
