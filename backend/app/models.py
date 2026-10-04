"""SQLAlchemy models for the AI Cockpit data model.

Hand-maintained copy of `input-orchestration/ai_cockpit_ingestion/models.py`
(separate deployments/images — no shared package at this prototype stage).
Mirrors `solution documentation/Logical Data Model.drawio`, which only the
Fachbereich edits: keep this file in sync with the diagram and with the
input-orchestration copy, never the other way round.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
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


class Initiative(Base):
    __tablename__ = "initiative"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, nullable=False)

    date_start = Column(DateTime, nullable=True)
    date_delivery = Column(DateTime, nullable=True)

    value_score = Column(Float, nullable=True)
    solution_complexity_score = Column(Float, nullable=True)

    owner_id = Column(Integer, ForeignKey("owner.id"), nullable=True)
    value_type_id = Column(Integer, ForeignKey("value_type.id"), nullable=True)
    solution_type_id = Column(Integer, ForeignKey("solution_type.id"), nullable=True)

    owner = relationship("Owner", back_populates="initiatives")
    value_type = relationship("ValueType", back_populates="initiatives")
    solution_type = relationship("SolutionType", back_populates="initiatives")
