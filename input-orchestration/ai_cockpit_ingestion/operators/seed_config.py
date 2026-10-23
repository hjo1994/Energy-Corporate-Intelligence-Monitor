"""Seed-Config operator: fills the config tables (Owner, SolutionType,
ValueType, RiskClassification) once.

These are configuration tables, maintained once and then only referenced:
silver links new initiatives to existing entries and never creates config
rows itself. This operator therefore only INSERTs entries that are missing
(matched by name) and never updates or deletes, so running it again is safe
and keeps any manual edits.

Sources:
- SolutionType / ValueType: the source workbook's "Variables" sheet
  ("Solution Type"/"Solution Type description", "Flagships/Pillars"/
  "Flagship description").
- RiskClassification: the five levels of the Rahmenbetriebsvereinbarung KI
  (transforms.risk_heuristic.RISK_LEVELS).
- Owner: the distinct Owner/Department pairs of the four extract tables,
  with the extract's business unit as category — so RawToBronze must have
  run at least once before.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
from airflow.sdk import BaseOperator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_cockpit_ingestion.db import get_engine
from ai_cockpit_ingestion.models import EXTRACT_TABLES, Owner, RiskClassification, SolutionType, ValueType
from ai_cockpit_ingestion.sources import SOURCES
from ai_cockpit_ingestion.transforms.normalize import clean_text
from ai_cockpit_ingestion.transforms.risk_heuristic import RISK_LEVELS


def _build_catalog(variables_df: pl.DataFrame, name_column: str, description_column: str) -> dict[str, str | None]:
    """Build an ordered {name: description} catalog from two columns of the
    Variables sheet, which lists several independent dropdown sources
    side by side in one sheet — only rows with a non-empty `name_column`
    value belong to this particular catalog.
    """
    catalog: dict[str, str | None] = {}
    for row in variables_df.iter_rows(named=True):
        name = clean_text(row.get(name_column))
        if name and name not in catalog:
            catalog[name] = clean_text(row.get(description_column))
    return catalog


class SeedConfigOperator(BaseOperator):
    template_fields = ("db_path", "source_dir")

    def __init__(self, *, db_path: str, source_dir: str, filename_glob: str, variables_sheet: str, **kwargs):
        super().__init__(**kwargs)
        self.db_path = db_path
        self.source_dir = source_dir
        self.filename_glob = filename_glob
        self.variables_sheet = variables_sheet

    def execute(self, context) -> None:
        candidates = [p for p in Path(self.source_dir).glob(self.filename_glob) if p.is_file()]
        if not candidates:
            raise FileNotFoundError(f"No file matching {self.filename_glob} in {self.source_dir}")
        source_file = max(candidates, key=lambda p: p.stat().st_mtime)
        self.log.info("Reading %s (sheet %r)", source_file, self.variables_sheet)
        variables_df = pl.read_excel(
            source_file, sheet_name=self.variables_sheet, engine="calamine", infer_schema_length=0
        )
        solution_types = _build_catalog(variables_df, "Solution Type", "Solution Type description")
        value_types = _build_catalog(variables_df, "Flagships/Pillars", "Flagship description")

        engine = get_engine(self.db_path)
        with Session(engine) as session, session.begin():
            added = {
                "solution_type": self._add_missing(session, SolutionType, solution_types),
                "value_type": self._add_missing(session, ValueType, value_types),
                "risk_classification": self._add_missing_risk_levels(session),
                "owner": self._add_missing_owners(session),
            }
        engine.dispose()
        self.log.info("Config seeded, new rows per table: %s", added)

    @staticmethod
    def _add_missing(session: Session, model, catalog: dict[str, str | None]) -> int:
        existing = set(session.scalars(select(model.name)))
        new = [model(name=name, description=desc) for name, desc in catalog.items() if name not in existing]
        session.add_all(new)
        return len(new)

    @staticmethod
    def _add_missing_risk_levels(session: Session) -> int:
        existing = set(session.scalars(select(RiskClassification.id)))
        new = [RiskClassification(**level) for level in RISK_LEVELS if level["id"] not in existing]
        session.add_all(new)
        return len(new)

    def _add_missing_owners(self, session: Session) -> int:
        existing = {
            (o.category, o.name, o.department or "") for o in session.scalars(select(Owner))
        }
        count = 0
        for source in SOURCES:
            table = EXTRACT_TABLES[source.extract_table]
            rows = session.execute(select(table.c["Owner"], table.c["Department"])).all()
            if not rows:
                self.log.warning("%s is empty — run RawToBronze first", source.extract_table)
            for owner_raw, department_raw in rows:
                name, department = clean_text(owner_raw), clean_text(department_raw)
                if not name:
                    continue
                key = (source.business_unit, name, department or "")
                if key in existing:
                    continue
                session.add(Owner(category=source.business_unit, name=name, department=department))
                existing.add(key)
                count += 1
        return count
