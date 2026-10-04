"""Raw-to-Silver operator: reads the source Excel with Polars, normalizes it
onto the AI Cockpit data model, and writes it into the shared SQLite file.

Interim architecture (see repo root README, "Interim-Entscheidung: SQLite-
Datei geteilt zwischen zwei Deployments"): this operator is the ONLY writer,
Backend only ever reads. It builds the full dataset in a fresh SQLite file
and swaps it into place with an atomic rename, so Backend (a separate
deployment) never observes a partially written database and no long-lived
write lock is held on the file it reads.

This is a full reimport on every run (no incremental diffing) — the
simplest correct behaviour for a dataset this size; revisit if the source
grows enough to make that slow.
"""
from __future__ import annotations

import os
from pathlib import Path

import polars as pl
from airflow.sdk import BaseOperator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ai_cockpit_ingestion import config
from ai_cockpit_ingestion.models import Base, Initiative, Owner, SolutionType, ValueType
from ai_cockpit_ingestion.transforms.normalize import (
    build_match_key_index,
    derive_solution_complexity_score,
    derive_timing_date,
    derive_value_score,
    match_catalog_name,
    normalize_status,
)

DEFAULT_SHEET_NAME = "EliaGroup"
DEFAULT_VARIABLES_SHEET_NAME = "Variables"


def _clean_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_catalog(variables_df: pl.DataFrame, name_column: str, description_column: str) -> dict[str, str | None]:
    """Build an ordered {name: description} catalog from two columns of the
    Variables sheet, which lists several independent dropdown sources
    side by side in one sheet — only rows with a non-empty `name_column`
    value belong to this particular catalog, unrelated to what the other
    columns hold in the same row.
    """
    catalog: dict[str, str | None] = {}
    for row in variables_df.iter_rows(named=True):
        name = _clean_str(row.get(name_column))
        if name and name not in catalog:
            catalog[name] = _clean_str(row.get(description_column))
    return catalog


class RawToSilverOperator(BaseOperator):
    """Reads `sensor_task_id`'s XCom-pushed source file, transforms it, and
    atomically replaces `db_path` with the result.
    """

    template_fields = ("db_path",)

    def __init__(
        self,
        *,
        db_path: str,
        sensor_task_id: str,
        sheet_name: str = DEFAULT_SHEET_NAME,
        variables_sheet_name: str = DEFAULT_VARIABLES_SHEET_NAME,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.db_path = db_path
        self.sensor_task_id = sensor_task_id
        self.sheet_name = sheet_name
        self.variables_sheet_name = variables_sheet_name

    def execute(self, context) -> None:
        ti = context["ti"]
        source_file_path = ti.xcom_pull(task_ids=self.sensor_task_id, key="source_file_path")
        source_file_mtime = ti.xcom_pull(task_ids=self.sensor_task_id, key="source_file_mtime")
        if not source_file_path:
            raise RuntimeError(
                f"No source_file_path in XCom from task {self.sensor_task_id!r} — "
                "the SourceFileSensor must run first"
            )

        self.log.info("Reading %s (sheet %r)", source_file_path, self.sheet_name)
        df = pl.read_excel(source_file_path, sheet_name=self.sheet_name, engine="calamine")
        df = df.filter(
            pl.col("Name").is_not_null() & (pl.col("Name").str.strip_chars() != "")
        )
        self.log.info("Read %d initiative rows", df.height)

        self.log.info("Reading %s (sheet %r) for the type catalogs", source_file_path, self.variables_sheet_name)
        variables_df = pl.read_excel(source_file_path, sheet_name=self.variables_sheet_name, engine="calamine")
        solution_type_catalog = _build_catalog(variables_df, "Solution Type", "Solution Type description")
        value_type_catalog = _build_catalog(variables_df, "Flagships/Pillars", "Flagship description")
        solution_type_match_index = build_match_key_index(list(solution_type_catalog))
        value_type_match_index = build_match_key_index(list(value_type_catalog))
        self.log.info(
            "Type catalogs: %d SolutionType, %d ValueType entries",
            len(solution_type_catalog),
            len(value_type_catalog),
        )

        db_path = Path(self.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = db_path.with_name(db_path.stem + ".new" + db_path.suffix)
        tmp_path.unlink(missing_ok=True)

        engine = create_engine(f"sqlite:///{tmp_path}")
        Base.metadata.create_all(engine)

        owner_cache: dict[tuple[str, str], Owner] = {}
        unmapped_status_count = 0
        unmapped_solution_type_count = 0
        unmapped_value_type_count = 0

        with Session(engine) as session:
            # SolutionType/ValueType are reference/lookup tables seeded from
            # the Variables sheet's own catalogs — not derived from
            # individual initiative rows.
            solution_type_rows = {
                name: SolutionType(name=name, description=description)
                for name, description in solution_type_catalog.items()
            }
            session.add_all(solution_type_rows.values())
            value_type_rows = {
                name: ValueType(name=name, description=description)
                for name, description in value_type_catalog.items()
            }
            session.add_all(value_type_rows.values())

            for row in df.iter_rows(named=True):
                name = _clean_str(row.get("Name"))
                if not name:
                    continue

                owner_name = _clean_str(row.get("Owner"))
                department = _clean_str(row.get("Department"))
                business_unit = _clean_str(row.get("Source"))

                owner = None
                if owner_name:
                    owner_key = (owner_name, department or "")
                    owner = owner_cache.get(owner_key)
                    if owner is None:
                        owner = Owner(
                            name=owner_name,
                            department=department,
                            category=business_unit,
                        )
                        session.add(owner)
                        owner_cache[owner_key] = owner

                solution_type_name = match_catalog_name(
                    row.get("Solution Type"),
                    canonical_names_by_match_key=solution_type_match_index,
                    initiative_name=name,
                    field_label="Solution Type",
                )
                if solution_type_name is None and row.get("Solution Type"):
                    unmapped_solution_type_count += 1
                solution_type = solution_type_rows.get(solution_type_name) if solution_type_name else None

                value_type_name = match_catalog_name(
                    row.get("Flagship"),
                    canonical_names_by_match_key=value_type_match_index,
                    initiative_name=name,
                    field_label="Flagship",
                )
                if value_type_name is None and row.get("Flagship"):
                    unmapped_value_type_count += 1
                value_type = value_type_rows.get(value_type_name) if value_type_name else None

                status = normalize_status(row.get("Status"), initiative_name=name)
                if status == "Unknown":
                    unmapped_status_count += 1

                initiative = Initiative(
                    name=name,
                    description=_clean_str(row.get("Description")),
                    status=status,
                    date_start=derive_timing_date(
                        row.get("Timing start"),
                        assumed_year=config.PLANNING_YEAR,
                        initiative_name=name,
                        field_label="Timing start",
                    ),
                    date_delivery=derive_timing_date(
                        row.get("Timing delivery"),
                        assumed_year=config.PLANNING_YEAR,
                        initiative_name=name,
                        field_label="Timing delivery",
                    ),
                    value_score=derive_value_score(row.get("Value")),
                    solution_complexity_score=derive_solution_complexity_score(
                        row.get("Solution Feasibility"), row.get("Complexity")
                    ),
                    owner=owner,
                    solution_type=solution_type,
                    value_type=value_type,
                )
                session.add(initiative)

            session.commit()

        engine.dispose()

        # Atomic swap on the same filesystem/PVC: Backend never sees a
        # half-written file, and the write lock window shrinks to this one
        # rename instead of the whole import.
        os.replace(tmp_path, db_path)
        self.log.info("Replaced %s with newly imported data (%d initiatives)", db_path, df.height)
        if unmapped_status_count:
            self.log.warning(
                "%d of %d initiatives had an unrecognized Status value, mapped to 'Unknown' "
                "— see preceding warnings for details",
                unmapped_status_count,
                df.height,
            )
        if unmapped_solution_type_count:
            self.log.warning(
                "%d of %d initiatives had a Solution Type that does not match the catalog "
                "(free text instead of a picked category) - solution_type_id left NULL",
                unmapped_solution_type_count,
                df.height,
            )
        if unmapped_value_type_count:
            self.log.warning(
                "%d of %d initiatives had a Flagship that does not match the catalog "
                "- value_type_id left NULL",
                unmapped_value_type_count,
                df.height,
            )

        if source_file_mtime is not None:
            marker = Path(source_file_path).parent / ".ai_cockpit_import.last_processed"
            marker.touch()
            os.utime(marker, (source_file_mtime, source_file_mtime))
